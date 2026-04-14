import frappe
from frappe import _
from frappe.model.document import Document


# ---------------------------------------------------------------------------
# Academic year helpers
# ---------------------------------------------------------------------------

@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_class_groups_with_annual_assessment(doctype, txt, searchfield, start, page_len, filters):
    """Custom search: only Class Groups that have an Annual Assessment."""
    import json
    if isinstance(filters, str):
        filters = json.loads(filters)
    filters = filters or {}

    academic_year = filters.get("academic_year")
    values = {"txt": f"%{txt}%", "start": int(start), "page_len": int(page_len)}

    conds = ["cg.is_active = 1", f"cg.`{searchfield}` LIKE %(txt)s"]
    if academic_year:
        conds.append("aa.academic_year = %(academic_year)s")
        values["academic_year"] = academic_year

    sql = """
        SELECT DISTINCT cg.name
        FROM `tabClass Group` cg
        INNER JOIN `tabAnnual Assessment` aa ON aa.class_group = cg.name
        WHERE {where}
        ORDER BY cg.name
        LIMIT %(start)s, %(page_len)s
    """.format(where=" AND ".join(conds))

    return frappe.db.sql(sql, values)


@frappe.whitelist()
def get_students_for_promotion(class_group):
    """Return active students in a class group for pre-populating promotion rows."""
    return frappe.db.get_all(
        "Student Group Assignment",
        filters={"class_group": class_group, "status": "Activa"},
        pluck="student",
        order_by="student asc",
    )


@frappe.whitelist()
def get_or_suggest_next_academic_year(academic_year):
    """
    Try to find the Academic Year that starts right after `academic_year` ends.

    Returns:
      {"found": True,  "name": "2026/2027"}
      {"found": False, "suggested_name": "2026/2027",
       "start_date": "2027-01-01", "end_date": "2027-12-31"}
      {"found": False, "error": "no_end_date"}
    """
    import re
    from frappe.utils import add_days

    end_date = frappe.db.get_value("Academic Year", academic_year, "end_date")
    if not end_date:
        return {"found": False, "error": "no_end_date"}

    next_start_min = add_days(end_date, 1)
    next_start_max = add_days(end_date, 90)

    row = frappe.db.sql(
        """SELECT name FROM `tabAcademic Year`
           WHERE start_date BETWEEN %s AND %s
           ORDER BY start_date ASC LIMIT 1""",
        (next_start_min, next_start_max),
        as_dict=True,
    )
    if row:
        return {"found": True, "name": row[0]["name"]}

    # Nothing found — build a suggestion from the name pattern
    from frappe.utils import add_years
    years = re.findall(r"\d{4}", str(academic_year))
    ay    = str(academic_year).strip()

    if len(years) == 1 and ay == years[0]:
        # Single-year naming: "2026" → "2027"
        suggested_name = str(int(years[0]) + 1)
    elif len(years) >= 2:
        # Range naming: "2025/2026" → "2026/2027"
        sep_m = re.search(r"\d{4}(.+?)\d{4}", ay)
        sep   = sep_m.group(1) if sep_m else "/"
        y2    = int(years[1])
        suggested_name = f"{y2}{sep}{y2 + 1}"
    elif len(years) == 1:
        suggested_name = str(int(years[0]) + 1)
    else:
        suggested_name = ""

    return {
        "found":            False,
        "suggested_name":   suggested_name,
        "start_date":  str(next_start_min),
        "end_date":    str(add_years(end_date, 1)),
    }


# ---------------------------------------------------------------------------
# Generate promotion rows from Annual Assessment
# ---------------------------------------------------------------------------

@frappe.whitelist()
def generate_promotion(doc_name):
    """
    Load promotion decisions from Annual Assessment.

    - Promovido → result == "Aprovado" and next_class exists
    - Concluído → result == "Aprovado" and no next_class (final class)
    - Retido    → result == "Reprovado"
    """
    doc = frappe.get_doc("Student Promotion", doc_name)

    ann_name = frappe.db.get_value(
        "Annual Assessment",
        {"academic_year": doc.academic_year, "class_group": doc.class_group},
        "name",
    )
    if not ann_name:
        return {"error": "no_annual_assessment"}

    ann_rows = frappe.db.get_all(
        "Annual Assessment Row",
        filters={"parent": ann_name},
        fields=["student", "final_grade", "result"],
        order_by="student asc",
    )
    if not ann_rows:
        return {"error": "no_rows"}

    next_class = frappe.db.get_value("School Class", doc.school_class, "next_class")
    is_final   = not next_class

    result_rows = []
    for row in ann_rows:
        aa_result = (row.result or "").strip()
        if aa_result == "Aprovado":
            decision = "Concluído" if is_final else "Promovido"
        else:
            decision = "Retido"

        result_rows.append({
            "student":     row.student,
            "final_grade": row.final_grade,
            "decision":    decision,
            "remarks":     "",
        })

    return result_rows


# ---------------------------------------------------------------------------
# Turma distribution — discovery and suggestion
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_promotion_turma_options(promotion_name):
    """
    Return existing turmas for the target classes and pre-computed
    placement suggestions for aprovados and reprovados.
    """
    doc = frappe.get_doc("Student Promotion", promotion_name)

    # Exclude students that already have an active enrolment for the next year
    # so that re-opening after a partial/full run shows the real remaining count.
    already_assigned = set()
    if doc.next_academic_year:
        already_assigned = set(frappe.db.get_all(
            "Student Group Assignment",
            filters={"academic_year": doc.next_academic_year, "status": "Activa"},
            pluck="student",
        ))

    all_aprovados  = [r for r in doc.promotion_rows if r.decision == "Promovido"]
    all_reprovados = [r for r in doc.promotion_rows if r.decision == "Retido"]

    aprovados  = [r for r in all_aprovados  if r.student not in already_assigned]
    concluidos = [r for r in doc.promotion_rows if r.decision == "Concluído"]
    reprovados = [r for r in all_reprovados if r.student not in already_assigned]

    default_cap = int(
        frappe.db.get_single_value("School Settings", "default_max_students_per_class") or 0
    )

    next_school_class = (
        frappe.db.get_value("School Class", doc.school_class, "next_class")
        if doc.school_class else None
    )

    def _get_groups(school_class, academic_year):
        if not school_class or not academic_year:
            return []
        return frappe.db.get_all(
            "Class Group",
            filters={"school_class": school_class, "academic_year": academic_year, "is_active": 1},
            fields=["name", "group_name", "max_students", "student_count"],
            order_by="creation asc",
        )

    target_groups   = _get_groups(next_school_class, doc.next_academic_year)
    retained_groups = _get_groups(doc.school_class,  doc.next_academic_year)

    return {
        "aprovados_count":              len(aprovados),
        "concluidos_count":             len(concluidos),
        "reprovados_count":             len(reprovados),
        "already_assigned_aprovados":   len(all_aprovados)  - len(aprovados),
        "already_assigned_reprovados":  len(all_reprovados) - len(reprovados),
        "next_school_class":            next_school_class,
        "school_class":                 doc.school_class,
        "next_academic_year":           doc.next_academic_year,
        "default_capacity":             default_cap,
        "target_groups":                target_groups,
        "retained_groups":              retained_groups,
        "aprovados_options": _build_aprovados_options(
            len(aprovados), target_groups, next_school_class,
            doc.next_academic_year, default_cap,
        ),
        "reprovados_options": _build_reprovados_options(
            len(reprovados), retained_groups, doc.school_class,
            doc.next_academic_year, default_cap,
        ),
    }


# ---------------------------------------------------------------------------
# Execute the confirmed distribution plan
# ---------------------------------------------------------------------------

@frappe.whitelist()
def execute_promotion_plan(promotion_name, plan):
    """
    1. Create any new Class Groups in the plan.
    2. Assign `assigned_class_group` on each promotion row.
    3. Create Student Group Assignments.
    4. Update student_count on affected Class Groups.
    5. Set promotion status to Finalizado.
    """
    doc  = frappe.get_doc("Student Promotion", promotion_name)
    plan = frappe.parse_json(plan) if isinstance(plan, str) else plan

    today = frappe.utils.today()

    # ── Step 1: Create new Class Groups ─────────────────────────────────────
    created_cg      = {}   # temp_id → actual doc.name
    created_cg_names = []
    affected_cgs    = set()

    for bucket in plan.get("aprovados", []) + plan.get("reprovados", []):
        if bucket["type"] == "new":
            tid = bucket["temp_id"]
            if tid not in created_cg:
                cg_doc = frappe.get_doc({
                    "doctype":       "Class Group",
                    "group_name":    bucket["name"],
                    "school_class":  bucket["school_class"],
                    "academic_year": bucket["academic_year"],
                    "max_students":  int(bucket.get("capacity") or 0),
                    "is_active":     1,
                    "student_count": 0,
                }).insert(ignore_permissions=True)
                created_cg[tid]  = cg_doc.name
                created_cg_names.append(cg_doc.group_name)
                affected_cgs.add(cg_doc.name)
        elif bucket["type"] == "existing":
            affected_cgs.add(bucket["class_group"])

    # ── Step 2: Assign students to class groups ──────────────────────────────
    def resolve_cg(bucket):
        if bucket["type"] == "existing":
            return bucket["class_group"]
        return created_cg.get(bucket["temp_id"])

    def assign_to_buckets(students, buckets):
        idx = 0
        for bucket in buckets:
            cg    = resolve_cg(bucket)
            count = int(bucket.get("count", 0))
            if not cg:
                continue
            for _ in range(count):
                if idx < len(students):
                    students[idx].assigned_class_group = cg
                    idx += 1

    aprovados  = sorted(
        [r for r in doc.promotion_rows if r.decision == "Promovido"],
        key=lambda r: r.student,
    )
    reprovados = sorted(
        [r for r in doc.promotion_rows if r.decision == "Retido"],
        key=lambda r: r.student,
    )

    assign_to_buckets(aprovados,  plan.get("aprovados",  []))
    assign_to_buckets(reprovados, plan.get("reprovados", []))

    doc.save(ignore_permissions=True)

    # ── Step 3: Create Student Group Assignments ─────────────────────────────
    created, skipped, errors = 0, 0, []

    for row in doc.promotion_rows:
        if not row.assigned_class_group:
            # Concluído or unassigned — no next enrolment
            skipped += 1
            continue

        if frappe.db.exists("Student Group Assignment", {
            "student":       row.student,
            "academic_year": doc.next_academic_year,
            "status":        "Activa",
        }):
            skipped += 1
            continue

        sc = frappe.db.get_value("Class Group", row.assigned_class_group, "school_class")

        try:
            frappe.get_doc({
                "doctype":         "Student Group Assignment",
                "student":         row.student,
                "academic_year":   doc.next_academic_year,
                "school_class":    sc,
                "class_group":     row.assigned_class_group,
                "assignment_date": today,
                "status":          "Activa",
                "notes":           _(
                    "Criado automaticamente pela Promoção {0}."
                ).format(doc.name),
            }).insert(ignore_permissions=True)
            created += 1
        except Exception as e:
            errors.append(f"{row.student}: {e}")

    # ── Step 4: Refresh student_count on affected turmas ────────────────────
    for cg_name in affected_cgs:
        cnt = frappe.db.count(
            "Student Group Assignment",
            {"class_group": cg_name, "status": "Activa"},
        )
        frappe.db.set_value("Class Group", cg_name, "student_count", cnt)

    # ── Step 5: Finalise ────────────────────────────────────────────────────
    doc.status = "Finalizado"
    doc.save(ignore_permissions=True)
    frappe.db.commit()

    return {
        "created":        created,
        "skipped":        skipped,
        "errors":         errors,
        "created_groups": created_cg_names,
    }


# ---------------------------------------------------------------------------
# Suggestion engine helpers
# ---------------------------------------------------------------------------

def _free(g):
    """Available spots. Returns 9999 when max_students is 0 (unlimited)."""
    if not g.max_students:
        return 9999
    return max(0, g.max_students - (g.student_count or 0))


def _bucket_existing(g, count):
    return {
        "type":        "existing",
        "class_group": g.name,
        "group_name":  g.group_name,
        "count":       count,
        "after":       (g.student_count or 0) + count,
        "max":         g.max_students or 0,
    }


def _turma_letter(n_existing, offset=0):
    return "ABCDEFGHIJKLMNOPQRSTUVWXYZ"[min(n_existing + offset, 25)]


def _turma_name(school_class, academic_year, n_existing, offset=0):
    """
    Build the turma group_name following the convention:
      {class_name} {letter}-{YY}
    Examples: 1ª Classe A-26  8ª Classe B-26  12ª Classe C-27
    """
    import re
    # Last 4-digit year in the academic_year string (e.g. "2025/2026" → 2026)
    years = re.findall(r"\d{4}", str(academic_year or ""))
    yy    = years[-1][-2:] if years else "??"

    class_name = frappe.db.get_value("School Class", school_class, "class_name") if school_class else None
    name_str   = class_name if class_name else (school_class or "?")

    letter = _turma_letter(n_existing, offset)
    return f"{name_str} {letter}-{yy}"


def _bucket_new(temp_id, school_class, academic_year, count, n_existing, default_cap, offset=0):
    return {
        "type":           "new",
        "temp_id":        temp_id,
        "suggested_name": _turma_name(school_class, academic_year, n_existing, offset),
        "school_class":   school_class,
        "academic_year":  academic_year,
        "count":          count,
        "capacity":       default_cap,
    }


def _distribute_evenly(count, groups):
    """Round-robin even distribution across groups."""
    n      = len(groups)
    base   = count // n
    extras = count % n
    result = []
    for i, g in enumerate(groups):
        c = base + (1 if i < extras else 0)
        if c > 0:
            result.append(_bucket_existing(g, c))
    return result


def _build_aprovados_options(count, groups, school_class, academic_year, default_cap):
    """
    Aprovados strategy: pack together, minimise number of turmas.
    """
    if count == 0:
        return []

    options    = []
    total_free = sum(_free(g) for g in groups)
    n_existing = len(groups)

    def _overfill_label(g, n):
        after = (g.student_count or 0) + n
        if g.max_students:
            return f"Ultrapassar o limite — colocar todos os {n} em {g.group_name} (ficaria com {after}/{g.max_students})"
        return f"Colocar todos os {n} em {g.group_name} (sem limite definido)"

    if not groups:
        # ── No existing turmas ──────────────────────────────────────────────
        options.append({
            "id": "all_new", "recommended": True, "warning": None,
            "label": f"Criar uma nova turma com todos os {count} aprovados",
            "buckets": [],
            "new_groups": [_bucket_new("apr_new_0", school_class, academic_year, count, 0, default_cap)],
        })
        if default_cap and count > default_cap * 0.7:
            h1, h2 = (count + 1) // 2, count // 2
            options.append({
                "id": "two_new", "recommended": False, "warning": None,
                "label": f"Criar 2 turmas mais equilibradas: {h1} + {h2} alunos",
                "buckets": [],
                "new_groups": [
                    _bucket_new("apr_new_0", school_class, academic_year, h1, 0, default_cap),
                    _bucket_new("apr_new_1", school_class, academic_year, h2, 0, default_cap, offset=1),
                ],
            })
        return options

    # Sort most-full first (pack strategy)
    by_full = sorted(groups, key=_free)

    if total_free >= count:
        # ── All fit in existing turmas ──────────────────────────────────────
        buckets, rem = [], count
        for g in by_full:
            if rem <= 0:
                break
            take = min(_free(g), rem)
            if take > 0:
                buckets.append(_bucket_existing(g, take))
                rem -= take
        options.append({
            "id": "pack", "recommended": True, "warning": None,
            "label": "Alocar nas turmas existentes: " + " + ".join(
                f"{b['count']} em {b['group_name']}" for b in buckets
            ),
            "buckets": buckets, "new_groups": [],
        })
    elif total_free > 0:
        # ── Partial fit: fill existing + create new ─────────────────────────
        buckets, rem = [], count
        for g in by_full:
            if rem <= 0:
                break
            take = min(_free(g), rem)
            if take > 0:
                buckets.append(_bucket_existing(g, take))
                rem -= take
        placed = count - rem
        options.append({
            "id": "partial_new", "recommended": True, "warning": None,
            "label": f"Alocar {placed} nas turmas existentes + criar nova turma para os {rem} restantes",
            "buckets": buckets,
            "new_groups": [_bucket_new("apr_new_0", school_class, academic_year, rem, n_existing, default_cap)],
        })
        # Overfill option
        most_full = by_full[0]
        options.append({
            "id": "overfill", "recommended": False, "warning": "overfill",
            "label": _overfill_label(most_full, count),
            "buckets": [_bucket_existing(most_full, count)],
            "new_groups": [],
        })
    else:
        # ── All existing turmas are full ────────────────────────────────────
        options.append({
            "id": "all_new_full", "recommended": True, "warning": None,
            "label": f"Criar nova turma para os {count} aprovados (turmas actuais estão cheias)",
            "buckets": [],
            "new_groups": [_bucket_new("apr_new_0", school_class, academic_year, count, n_existing, default_cap)],
        })
        most_full = by_full[0]
        options.append({
            "id": "overfill", "recommended": False, "warning": "overfill",
            "label": _overfill_label(most_full, count),
            "buckets": [_bucket_existing(most_full, count)],
            "new_groups": [],
        })

    # Always offer "create new for all" as alternative
    options.append({
        "id": "all_new_alt", "recommended": False, "warning": None,
        "label": f"Criar nova turma separada com todos os {count} aprovados",
        "buckets": [],
        "new_groups": [_bucket_new("apr_new_0", school_class, academic_year, count, n_existing, default_cap)],
    })

    return options


def _build_reprovados_options(count, groups, school_class, academic_year, default_cap):
    """
    Reprovados strategy: spread across turmas so repetentes are not isolated.
    """
    if count == 0:
        return []

    options    = []
    n_existing = len(groups)

    if not groups:
        options.append({
            "id": "all_new", "recommended": True, "warning": None,
            "label": f"Criar nova turma com todos os {count} repetentes",
            "buckets": [],
            "new_groups": [_bucket_new("ret_new_0", school_class, academic_year, count, 0, default_cap)],
        })
        return options

    # ── Spread evenly across existing turmas (recommended) ──────────────────
    spread = _distribute_evenly(count, groups)
    fits   = all(not b["max"] or b["after"] <= b["max"] for b in spread)

    options.append({
        "id": "spread", "recommended": fits, "warning": None if fits else "overfill",
        "label": "Distribuir pelas turmas existentes: " + " + ".join(
            f"{b['count']} em {b['group_name']}" for b in spread
        ),
        "buckets": spread, "new_groups": [],
    })

    if not fits:
        # ── Spread into free capacity + create new for overflow ──────────────
        buckets, rem = [], count
        for g in groups:
            free = _free(g)
            if free > 0 and rem > 0:
                take = min(free, rem)
                buckets.append(_bucket_existing(g, take))
                rem -= take
        if rem > 0:
            placed = count - rem
            new_g = _bucket_new("ret_new_0", school_class, academic_year, rem, n_existing, default_cap)
            options.insert(0, {
                "id": "spread_new", "recommended": True, "warning": None,
                "label": f"Distribuir {placed} pelas existentes + criar nova turma para os {rem} restantes",
                "buckets": buckets,
                "new_groups": [new_g],
            })

    # ── Per-group individual options (not recommended) ──────────────────────
    for g in groups:
        over = count > _free(g) and bool(g.max_students)
        after = (g.student_count or 0) + count
        cap_note = f" (ficaria com {after}/{g.max_students})" if g.max_students else ""
        options.append({
            "id": f"all_{g.name}", "recommended": False,
            "warning": "overfill" if over else "not_recommended",
            "label": (
                f"{'Ultrapassar o limite — t' if over else 'T'}odos os {count} em {g.group_name}{cap_note}"
            ),
            "buckets": [_bucket_existing(g, count)],
            "new_groups": [],
        })

    # ── Create new for all (not recommended when existing groups available) ──
    options.append({
        "id": "ret_all_new", "recommended": False, "warning": "not_recommended",
        "label": f"Criar nova turma separada com todos os {count} repetentes",
        "buckets": [],
        "new_groups": [_bucket_new("ret_new_0", school_class, academic_year, count, n_existing, default_cap)],
    })

    return options


# ---------------------------------------------------------------------------
# Document class
# ---------------------------------------------------------------------------

class StudentPromotion(Document):
    def validate(self):
        self._validate_class_group_compatibility()
        self._validate_uniqueness()
        self._validate_annual_assessment_exists()

    def _validate_class_group_compatibility(self):
        if not self.class_group:
            return
        cg = frappe.db.get_value(
            "Class Group", self.class_group,
            ["academic_year", "school_class"], as_dict=True,
        )
        if not cg:
            return
        if cg.academic_year != self.academic_year:
            frappe.throw(
                _(
                    "A Turma <b>{0}</b> pertence ao Ano Lectivo <b>{1}</b>, "
                    "não ao Ano Lectivo <b>{2}</b>."
                ).format(self.class_group, cg.academic_year, self.academic_year),
                title=_("Turma incompatível"),
            )
        if self.school_class and cg.school_class != self.school_class:
            frappe.throw(
                _(
                    "A Turma <b>{0}</b> pertence à Classe <b>{1}</b>, "
                    "não à Classe <b>{2}</b>."
                ).format(self.class_group, cg.school_class, self.school_class),
                title=_("Classe incompatível"),
            )

    def _validate_uniqueness(self):
        existing = frappe.db.get_value(
            "Student Promotion",
            {
                "academic_year": self.academic_year,
                "class_group":   self.class_group,
                "name":          ("!=", self.name),
            },
            "name",
        )
        if existing:
            frappe.throw(
                _(
                    "Já existe uma Promoção de Alunos para a Turma <b>{0}</b> "
                    "no Ano Lectivo <b>{1}</b>: <b>{2}</b>."
                ).format(self.class_group, self.academic_year, existing),
                title=_("Promoção duplicada"),
            )

    def _validate_annual_assessment_exists(self):
        if not (self.academic_year and self.class_group):
            return
        ann = frappe.db.get_value(
            "Annual Assessment",
            {"academic_year": self.academic_year, "class_group": self.class_group},
            "name",
        )
        if not ann:
            frappe.throw(
                _(
                    "Não existe uma Avaliação Anual para a Turma <b>{0}</b> "
                    "no Ano Lectivo <b>{1}</b>. Crie e calcule a Avaliação Anual primeiro."
                ).format(self.class_group, self.academic_year),
                title=_("Avaliação Anual em falta"),
            )
