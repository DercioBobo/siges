import frappe
from frappe import _

_INACTIVE_STATUSES = ("Desistente", "Transferido", "Concluiu")


@frappe.whitelist()
def get_filter_options():
    years = frappe.db.get_all(
        "Academic Year", fields=["name", "year_name", "start_date"], order_by="start_date desc"
    )
    classes = frappe.db.get_all(
        "School Class", filters={"is_active": 1},
        fields=["name", "class_name", "class_level"], order_by="class_level asc",
    )
    # Default to the most recent year that still has students waiting for a turma.
    default_year = None
    for y in years:
        if _pending_rows(y.name):
            default_year = y.name
            break
    if not default_year:
        default_year = frappe.db.get_single_value("School Settings", "current_academic_year")
    return {"years": years, "classes": classes, "default_year": default_year}


def _pending_rows(academic_year, school_class=None):
    """Students with a submitted Inscrição for the year and no active turma in that year."""
    class_sql = "AND i.school_class = %(school_class)s" if school_class else ""
    return frappe.db.sql(f"""
        SELECT i.name AS inscricao, i.student, i.school_class, i.enrollment_date,
               i.enrollment_type, s.full_name AS student_name, s.gender
        FROM `tabInscricao` i
        JOIN `tabStudent` s ON s.name = i.student
        WHERE i.docstatus = 1
          AND i.academic_year = %(academic_year)s
          {class_sql}
          AND s.current_status NOT IN %(inactive)s
          AND NOT EXISTS (
              SELECT 1 FROM `tabStudent Group Assignment` sga
              WHERE sga.student = i.student
                AND sga.academic_year = i.academic_year
                AND sga.status = 'Activa'
          )
        ORDER BY s.full_name ASC
    """, {"academic_year": academic_year, "school_class": school_class, "inactive": _INACTIVE_STATUSES},
        as_dict=True)


def _turmas(academic_year, school_classes):
    if not school_classes:
        return []
    groups = frappe.db.get_all(
        "Class Group",
        filters={"academic_year": academic_year, "school_class": ("in", list(school_classes)), "is_active": 1},
        fields=["name", "group_name", "school_class", "shift", "classroom", "max_students"],
        order_by="group_name asc",
    )
    # Live count — student_count on Class Group can lag behind the SGAs.
    counts = dict(frappe.db.sql("""
        SELECT class_group, COUNT(*) FROM `tabStudent Group Assignment`
        WHERE academic_year = %s AND status = 'Activa'
        GROUP BY class_group
    """, academic_year))
    for g in groups:
        g.student_count = counts.get(g.name, 0)
    return groups


@frappe.whitelist()
def get_allocation_data(academic_year, school_class=None):
    pending = _pending_rows(academic_year, school_class)

    class_names = {r.school_class for r in pending}
    if school_class:
        class_names.add(school_class)

    turmas = _turmas(academic_year, class_names)

    meta = {
        c.name: c for c in frappe.db.get_all(
            "School Class", filters={"name": ("in", list(class_names) or [""])},
            fields=["name", "class_name", "class_level"],
        )
    }

    sections = []
    for cls in class_names:
        sections.append({
            "school_class": cls,
            "class_name": meta[cls].class_name if cls in meta else cls,
            "class_level": meta[cls].class_level if cls in meta else 0,
            "pending": [r for r in pending if r.school_class == cls],
            "turmas": [g for g in turmas if g.school_class == cls],
        })
    sections.sort(key=lambda s: (s["class_level"] or 0, s["class_name"]))

    return {"academic_year": academic_year, "total_pending": len(pending), "sections": sections}


@frappe.whitelist()
def allocate(class_group, students):
    """Allocate pending students to a turma. Reuses Class Group's bulk add (enrolment gate + SGA)."""
    from escola.escola.doctype.class_group.class_group import add_students_to_group
    from escola.escola.doctype.student.student import student_label

    students = frappe.parse_json(students) if isinstance(students, str) else students
    cg = frappe.db.get_value("Class Group", class_group, ["academic_year", "school_class", "is_active"], as_dict=True)
    if not cg or not cg.is_active:
        frappe.throw(_("A Turma <b>{0}</b> não existe ou não está activa.").format(class_group))

    valid, errors = [], []
    for student in students:
        insc_class = frappe.db.get_value(
            "Inscricao", {"student": student, "academic_year": cg.academic_year, "docstatus": 1}, "school_class"
        )
        if insc_class and insc_class != cg.school_class:
            errors.append({
                "student": student_label(student),
                "error": _("Inscrito na {0}, não na {1}.").format(insc_class, cg.school_class),
            })
        else:
            valid.append(student)

    result = add_students_to_group(class_group, valid) if valid else {"created": 0, "skipped": 0, "errors": []}
    result["errors"] = errors + result["errors"]
    return result


def _distribution_plan(academic_year, school_class):
    """Spread pending students across the class's turmas: least-filled first, genders interleaved."""
    pending = _pending_rows(academic_year, school_class)
    turmas = _turmas(academic_year, [school_class])

    # Interleave by gender so each turma gets a balanced mix.
    by_gender = {}
    for r in pending:
        by_gender.setdefault(r.gender or "", []).append(r)
    queues = list(by_gender.values())
    ordered = []
    while any(queues):
        for q in queues:
            if q:
                ordered.append(q.pop(0))

    load = {g.name: g.student_count for g in turmas}
    cap = {g.name: (g.max_students or 0) for g in turmas}
    plan = {g.name: [] for g in turmas}
    leftover = []
    for r in ordered:
        open_turmas = [g for g in load if not cap[g] or load[g] < cap[g]]
        if not open_turmas:
            leftover.append(r.student)
            continue
        # Lowest occupancy ratio first; unlimited turmas compare by raw count.
        target = min(open_turmas, key=lambda g: (load[g] / cap[g]) if cap[g] else load[g] / 1000)
        plan[target].append(r.student)
        load[target] += 1

    names = {g.name: g.group_name for g in turmas}
    return plan, names, leftover


@frappe.whitelist()
def auto_allocate(academic_year, school_class, dry_run=1):
    plan, names, leftover = _distribution_plan(academic_year, school_class)
    summary = [{"class_group": cg, "group_name": names[cg], "count": len(s)} for cg, s in plan.items() if s]

    if frappe.utils.cint(dry_run):
        return {"plan": summary, "leftover": len(leftover)}

    created, errors = 0, []
    for cg, students in plan.items():
        if not students:
            continue
        res = allocate(cg, students)
        created += res.get("created", 0)
        errors += res.get("errors", [])
    return {"created": created, "errors": errors, "leftover": len(leftover)}
