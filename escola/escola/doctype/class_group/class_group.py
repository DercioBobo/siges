import frappe
from frappe import _
from frappe.model.document import Document


class ClassGroup(Document):
    def before_delete(self):
        active = frappe.db.count(
            "Student Group Assignment",
            {"class_group": self.name, "status": "Activa"},
        )
        if active:
            frappe.throw(
                _("Não é possível eliminar a Turma <b>{0}</b> porque tem <b>{1}</b> aluno(s) activo(s). "
                  "Encerre todas as alocações antes de eliminar.").format(self.name, active),
                title=_("Turma com alunos"),
            )

    def validate(self):
        if not self.is_new():
            self._validate_structural_fields()
        self._validate_class_teacher()
        self._validate_no_duplicate_subjects()
        self._validate_deactivation()
        if self.max_students and self.max_students < 0:
            frappe.throw(
                _("A Capacidade Máxima não pode ser negativa. Deixe em branco ou a zero para turma ilimitada."),
                title=_("Capacidade inválida"),
            )

    def _validate_deactivation(self):
        if self.is_active:
            return
        before = self.get_doc_before_save()
        if not before or not before.is_active:
            return
        active = frappe.db.count(
            "Student Group Assignment",
            {"class_group": self.name, "status": "Activa"},
        )
        if active:
            frappe.throw(
                _("Não é possível desactivar a Turma <b>{0}</b> enquanto tiver <b>{1}</b> aluno(s) activo(s). "
                  "Encerre ou transfira todas as alocações primeiro.").format(self.name, active),
                title=_("Turma com alunos activos"),
            )

    def _validate_no_duplicate_subjects(self):
        seen = set()
        for row in self.subject_teachers or []:
            if not row.subject:
                continue
            if row.subject in seen:
                frappe.throw(
                    _("A disciplina <b>{0}</b> aparece mais do que uma vez na tabela de Disciplinas e Professores.").format(row.subject),
                    title=_("Disciplina duplicada"),
                )
            seen.add(row.subject)

    def _validate_structural_fields(self):
        before = self.get_doc_before_save()
        if not before:
            return
        changed = (
            before.school_class != self.school_class
            or before.academic_year != self.academic_year
        )
        if not changed:
            return
        has_assignments = frappe.db.exists(
            "Student Group Assignment", {"class_group": self.name}
        )
        if has_assignments:
            frappe.throw(
                _("Não é possível alterar a <b>Classe</b> ou o <b>Ano Lectivo</b> "
                  "de uma turma que já tem alunos alocados. "
                  "Encerre todas as alocações antes de fazer esta alteração."),
                title=_("Turma com alocações"),
            )

    def _validate_class_teacher(self):
        if not self.class_teacher:
            return
        is_active = frappe.db.get_value("Teacher", self.class_teacher, "is_active")
        if not is_active:
            frappe.throw(
                _("O professor <b>{0}</b> não está activo e não pode ser designado "
                  "como Director de Turma.").format(self.class_teacher),
                title=_("Professor inactivo"),
            )
        # Warn (not block) if already Director de Turma in another Class Group this year
        if not self.academic_year:
            return
        other = frappe.db.get_value(
            "Class Group",
            {
                "class_teacher": self.class_teacher,
                "academic_year": self.academic_year,
                "name": ("!=", self.name or ""),
            },
            ["name", "group_name"],
            as_dict=True,
        )
        if other:
            frappe.msgprint(
                _("Atenção: o professor já é Director de Turma de "
                  "<a href='/app/class-group/{0}'><b>{1}</b></a> "
                  "no mesmo Ano Lectivo.").format(other.name, other.group_name),
                title=_("Director de Turma em múltiplas turmas"),
                indicator="orange",
            )


@frappe.whitelist()
def get_subjects_for_school_class(school_class):
    """Return subjects + teachers defined on a School Class. Called on new Class Group forms."""
    rows = frappe.db.get_all(
        "School Class Subject",
        filters={"parent": school_class},
        fields=["subject", "teacher"],
        order_by="sort_order asc, idx asc",
    )
    subject_names = [r.subject for r in rows if r.subject]
    specialist_set = set(frappe.get_all(
        "Subject",
        filters={"name": ("in", subject_names), "is_specialist": 1},
        pluck="name",
    )) if subject_names else set()
    return [
        {
            "subject":       row.subject,
            "teacher":       row.teacher or "",
            "is_specialist": 1 if row.subject in specialist_set else 0,
        }
        for row in rows if row.subject
    ]


@frappe.whitelist()
def get_subjects_for_class_group(class_group):
    """Used by the 'Preencher Disciplinas' button on saved Class Group forms.

    Resolves the teacher per subject according to the turma's teaching model:
    - "Professor Único" (Primário/Pré-Primário): the Director de Turma teaches every
      non-specialist subject; specialist subjects keep their own teacher.
    - "Professores por Disciplina" (Secundário): teacher comes from the School Class
      subject table (unchanged behaviour).
    """
    cg = frappe.db.get_value(
        "Class Group", class_group,
        ["school_class", "teaching_model", "class_teacher"],
        as_dict=True,
    )
    if not cg or not cg.school_class:
        return []
    subjects = get_subjects_for_school_class(cg.school_class)
    if cg.teaching_model == "Professor Único" and cg.class_teacher:
        for s in subjects:
            if not s["is_specialist"]:
                s["teacher"] = cg.class_teacher
    return subjects


@frappe.whitelist()
def get_class_group_health(class_group):
    """Return a list of health-check items for the Class Group form badge."""
    cg = frappe.db.get_value(
        "Class Group", class_group,
        ["class_teacher", "school_class", "student_count", "teaching_model", "classroom", "academic_year"],
        as_dict=True,
    )
    if not cg:
        return []

    items = []

    # Director de Turma — critical for all models
    items.append({
        "label":    _("Director de Turma"),
        "status":   "ok" if cg.class_teacher else "err",
        "detail":   cg.class_teacher or None,
        "route":    None,
    })

    # Disciplinas e Professores — only meaningful for Professores por Disciplina
    if cg.teaching_model == "Professores por Disciplina":
        rows = frappe.db.get_all(
            "Class Group Subject Line",
            filters={"parent": class_group},
            fields=["subject", "teacher"],
        )
        missing = [r.subject for r in rows if not r.teacher]
        if not rows:
            status, detail = "err", _("sem disciplinas")
        elif missing:
            status = "warn"
            detail = _("{0} disciplina(s), {1} sem professor").format(len(rows), len(missing))
        else:
            status = "ok"
            detail = _("{0} disciplina(s)").format(len(rows))
        items.append({"label": _("Disciplinas"), "status": status, "detail": detail, "route": None})

    # Alunos inscritos — warn if 0 (may be fine early in year)
    count = int(cg.student_count or 0)
    items.append({
        "label":  _("Alunos"),
        "status": "ok" if count > 0 else "warn",
        "detail": _("{0} aluno(s)").format(count),
        "route":  None,
    })

    # Sala — minor warning
    items.append({
        "label":  _("Sala"),
        "status": "ok" if cg.classroom else "warn",
        "detail": cg.classroom or _("não definida"),
        "route":  None,
    })

    # Horário activo — critical
    timetable = frappe.db.get_value(
        "Timetable", {"class_group": class_group, "status": "Activo"}, "name"
    )
    items.append({
        "label":  _("Horário"),
        "status": "ok" if timetable else "err",
        "detail": timetable or None,
        "route":  f"/app/timetable/{timetable}" if timetable else None,
        "action": None if timetable else {
            "label":    _("Criar"),
            "doctype":  "Timetable",
            "values":   {"class_group": class_group, "academic_year": cg.academic_year},
        },
    })

    # Billing Schedule — critical (school class level)
    if cg.school_class:
        billing = frappe.db.get_value(
            "Billing Schedule",
            {"school_class": cg.school_class, "is_active": 1},
            "name",
        )
        items.append({
            "label":  _("Cobrança"),
            "status": "ok" if billing else "err",
            "detail": billing or None,
            "route":  f"/app/billing-schedule/{billing}" if billing else None,
            "action": None if billing else {
                "label": _("Configurar"),
                "route": f"/app/billing-schedule/new-billing-schedule-1",
            },
        })

        # Fee Structure — critical (school class level)
        fee = frappe.db.get_value(
            "Fee Structure",
            {"school_class": cg.school_class, "is_active": 1},
            "name",
        )
        items.append({
            "label":  _("Tarifas"),
            "status": "ok" if fee else "err",
            "detail": fee or None,
            "route":  f"/app/fee-structure/{fee}" if fee else None,
            "action": None if fee else {
                "label": _("Configurar"),
                "route": "/app/fee-structure/new-fee-structure-1",
            },
        })

    return items


@frappe.whitelist()
def search_students_for_group(class_group, query=""):
    """
    Returns students (Activo + Pendente de Turma) enriched with their active SGA
    for this class_group's academic year, so the UI can show who is already in another turma.
    """
    cg = frappe.db.get_value("Class Group", class_group, "academic_year")
    if not cg:
        return []

    filters = [["current_status", "in", ["Activo", "Pendente de Turma"]]]
    if query:
        filters.append(["full_name", "like", f"%{query}%"])

    students = frappe.db.get_all(
        "Student",
        filters=filters,
        fields=["name", "full_name", "current_status"],
        limit=60,
        order_by="full_name asc",
    )
    if not students:
        return []

    student_names = [s.name for s in students]

    sgas = frappe.db.get_all(
        "Student Group Assignment",
        filters={"student": ("in", student_names), "academic_year": cg, "status": "Activa"},
        fields=["student", "class_group"],
    )
    sga_map = {s.student: s.class_group for s in sgas}

    cg_needed = set(sga_map.values())
    cg_labels = {}
    if cg_needed:
        for r in frappe.db.get_all("Class Group", filters={"name": ("in", list(cg_needed))}, fields=["name", "group_name"]):
            cg_labels[r.name] = r.group_name

    return [
        {
            "name":               s.name,
            "full_name":          s.full_name,
            "current_status":     s.current_status,
            "current_turma":      sga_map.get(s.name),
            "current_turma_name": cg_labels.get(sga_map.get(s.name)),
        }
        for s in students
    ]


def _check_enrollment_gate(student, academic_year):
    """Block adding a student to a turma unless a submitted enrollment document exists for that year."""
    has_inscricao = frappe.db.exists(
        "Inscricao", {"student": student, "academic_year": academic_year, "docstatus": 1}
    )
    if has_inscricao:
        return
    has_renovacao = frappe.db.exists(
        "Renovacao De Matricula",
        {"student": student, "target_academic_year": academic_year, "docstatus": 1},
    )
    if has_renovacao:
        return
    student_name = frappe.db.get_value("Student", student, "full_name") or student
    frappe.throw(
        _("O aluno <b>{0}</b> não tem Inscrição nem Renovação de Matrícula submetida "
          "para o Ano Lectivo <b>{1}</b>. "
          "Submeta o documento adequado antes de atribuir uma turma.").format(
            student_name, academic_year
        ),
        title=_("Matrícula em falta"),
    )


@frappe.whitelist()
def add_students_to_group(class_group_name, students):
    """
    Bulk-create Student Group Assignments for a list of students.
    `students` is a JSON-encoded list of student names.
    """
    import json
    if isinstance(students, str):
        students = json.loads(students)

    cg_data = frappe.db.get_value(
        "Class Group", class_group_name,
        ["academic_year", "school_class"], as_dict=True
    )
    today = frappe.utils.today()
    created, skipped, errors = [], [], []

    for student in students:
        if frappe.db.exists("Student Group Assignment", {
            "student": student,
            "class_group": class_group_name,
            "status": "Activa",
        }):
            skipped.append(student)
            continue
        try:
            _check_enrollment_gate(student, cg_data.academic_year)
            frappe.get_doc({
                "doctype": "Student Group Assignment",
                "student": student,
                "class_group": class_group_name,
                "academic_year": cg_data.academic_year,
                "school_class": cg_data.school_class,
                "assignment_date": today,
                "status": "Activa",
            }).insert()
            created.append(student)
        except frappe.ValidationError as e:
            errors.append({"student": student, "error": str(e)})

    frappe.db.commit()
    return {"created": len(created), "skipped": len(skipped), "errors": errors}


@frappe.whitelist()
def remove_student_from_group(class_group_name, student):
    """
    Mark a student's active SGA as Encerrada, which triggers the roster sync hook.
    """
    sga_name = frappe.db.get_value(
        "Student Group Assignment",
        {"student": student, "class_group": class_group_name, "status": "Activa"},
        "name",
    )
    if not sga_name:
        frappe.throw(
            _("Não foi encontrada uma alocação activa para este aluno nesta turma."),
            title=_("Alocação não encontrada"),
        )
    frappe.db.set_value("Student Group Assignment", sga_name, "status", "Encerrada")
    frappe.db.commit()
    # Trigger roster sync manually since we bypassed save()
    from escola.escola.doctype.student_group_assignment.student_group_assignment import (
        _roster_sync, _sync_student_current_turma,
    )
    sga = frappe.get_doc("Student Group Assignment", sga_name)
    _roster_sync(sga)
    _sync_student_current_turma(sga)
    return sga_name


@frappe.whitelist()
def rebuild_roster(class_group_name):
    """
    Rebuild the student roster from active Student Group Assignments.
    Safe to call at any time — idempotent.
    """
    frappe.db.delete("Class Group Student", {"parent": class_group_name})

    assignments = frappe.get_all(
        "Student Group Assignment",
        filters={"class_group": class_group_name, "status": "Activa"},
        fields=["name", "student"],
        order_by="student asc",
    )

    for idx, sga in enumerate(assignments, start=1):
        frappe.get_doc({
            "doctype": "Class Group Student",
            "parent": class_group_name,
            "parentfield": "students",
            "parenttype": "Class Group",
            "idx": idx,
            "student": sga.student,
            "assignment": sga.name,
        }).insert(ignore_permissions=True)

    count = len(assignments)
    frappe.db.set_value(
        "Class Group", class_group_name, "student_count", count, update_modified=False
    )
    frappe.db.commit()
    return count


@frappe.whitelist()
def sync_class_group_students(class_group_name):
    """
    Update student_name for all students in the roster and remove those
    whose current_status is no longer 'Activo'.
    """
    doc = frappe.get_doc("Class Group", class_group_name)
    if not doc.students:
        return {"removed": 0, "updated": 0, "kept": 0}

    student_ids = [row.student for row in doc.students]
    student_data = frappe.get_all(
        "Student",
        filters={"name": ("in", student_ids)},
        fields=["name", "current_status", "full_name"],
    )
    data_map = {s.name: s for s in student_data}

    kept, removed, updated = [], 0, 0
    for row in doc.students:
        s = data_map.get(row.student)
        if not s or s.current_status != "Activo":
            removed += 1
            continue
        if s.full_name and row.student_name != s.full_name:
            row.student_name = s.full_name
            updated += 1
        kept.append(row)

    if removed or updated:
        doc.set("students", kept)
        doc.save(ignore_permissions=True)

    return {"removed": removed, "updated": updated, "kept": len(kept)}


def sync_student_in_rosters(doc, method=None):
    """
    Called via doc_events when a Student record is saved.
    Updates student_name in every Class Group Student row for this student.
    """
    if not doc.full_name:
        return
    frappe.db.sql(
        """UPDATE `tabClass Group Student`
           SET student_name = %s
           WHERE student = %s""",
        (doc.full_name, doc.name),
    )
