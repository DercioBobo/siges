import frappe
from frappe import _


@frappe.whitelist()
def get_filter_options():
    class_groups = frappe.get_all(
        "Class Group",
        filters={"is_active": 1},
        fields=["name", "group_name", "school_class", "academic_year"],
        order_by="group_name asc",
    )
    years = frappe.get_all(
        "Academic Year",
        fields=["name", "year"],
        order_by="year desc",
    )
    return {"class_groups": class_groups, "years": years}


@frappe.whitelist()
def get_pauta_data(class_group, academic_year):
    """Compile all data needed to render the Pauta de Frequência."""
    cg = frappe.db.get_value(
        "Class Group", class_group,
        ["group_name", "school_class", "classroom", "shift", "class_teacher"],
        as_dict=True,
    )
    if not cg:
        frappe.throw(_("Turma não encontrada."))

    school_name = frappe.db.get_single_value("School Settings", "school_name") or ""
    min_passing = float(
        frappe.db.get_value("School Class", cg.school_class, "minimum_passing_grade")
        or frappe.db.get_single_value("School Settings", "minimum_passing_grade")
        or 10
    )

    terms = frappe.get_all(
        "Academic Term",
        filters={"academic_year": academic_year},
        fields=["name", "term_name", "start_date"],
        order_by="start_date asc",
    )
    if not terms:
        frappe.throw(_("Nenhum período lectivo encontrado para este Ano Lectivo."))

    term_position = {t.name: idx + 1 for idx, t in enumerate(terms)}

    students = frappe.db.sql(
        """
        SELECT sga.student, s.full_name AS student_name, s.gender, s.student_code
        FROM `tabStudent Group Assignment` sga
        JOIN `tabStudent` s ON s.name = sga.student
        WHERE sga.class_group = %s AND sga.academic_year = %s AND sga.status = 'Activa'
        ORDER BY s.full_name
        """,
        (class_group, academic_year),
        as_dict=True,
    )

    # Subjects from active curriculum
    curriculum = frappe.db.get_value(
        "Class Curriculum",
        {"class_group": class_group, "is_active": 1},
        "name",
    )
    subjects = []
    if curriculum:
        lines = frappe.get_all(
            "Class Curriculum Line",
            filters={"parent": curriculum},
            fields=["subject"],
            order_by="idx asc",
        )
        sn_list = [l.subject for l in lines if l.subject]
        if sn_list:
            subj_infos = {
                s.name: s
                for s in frappe.get_all(
                    "Subject",
                    filters={"name": ("in", sn_list)},
                    fields=["name", "subject_name", "subject_code"],
                )
            }
            subjects = [
                {
                    "name": sn,
                    "subject_name": subj_infos[sn].subject_name,
                    "subject_code": subj_infos[sn].subject_code or sn[:4].upper(),
                }
                for sn in sn_list if sn in subj_infos
            ]

    # Grades: student → subject → term_pos → mt
    grade_data = {}
    grade_entries = frappe.get_all(
        "Grade Entry",
        filters={
            "class_group": class_group,
            "academic_year": academic_year,
            "docstatus": ("!=", 2),
        },
        fields=["name", "academic_term", "subject"],
    )
    for ge in grade_entries:
        pos = term_position.get(ge.academic_term)
        if not pos:
            continue
        rows = frappe.get_all(
            "Grade Entry Row",
            filters={"parent": ge.name, "is_absent": 0},
            fields=["student", "mt"],
        )
        for row in rows:
            if row.mt is None:
                continue
            grade_data.setdefault(row.student, {}).setdefault(ge.subject, {})[pos] = float(row.mt)

    # Attendance and comportamento: student → term_pos → data
    attendance_data = {}
    comportamento_data = {}
    for term in terms:
        pos = term_position[term.name]
        ta_name = frappe.db.get_value(
            "Term Attendance",
            {"class_group": class_group, "academic_term": term.name, "docstatus": ("!=", 2)},
            "name",
        )
        if not ta_name:
            continue
        rows = frappe.get_all(
            "Term Attendance Row",
            filters={"parent": ta_name},
            fields=["student", "justified_absences", "unjustified_absences", "total_absences", "comportamento"],
        )
        for row in rows:
            attendance_data.setdefault(row.student, {})[pos] = {
                "justified": row.justified_absences or 0,
                "unjustified": row.unjustified_absences or 0,
                "total": row.total_absences or 0,
            }
            if row.comportamento:
                comportamento_data.setdefault(row.student, {})[pos] = row.comportamento

    # Annual assessment results (if available)
    ann = frappe.db.get_value(
        "Annual Assessment",
        {"class_group": class_group, "academic_year": academic_year},
        "name",
    )
    result_map = {}
    if ann:
        for r in frappe.get_all(
            "Annual Assessment Row",
            filters={"parent": ann},
            fields=["student", "result", "final_grade"],
        ):
            result_map[r.student] = r

    n_terms = len(terms)
    student_rows = []
    for idx, s in enumerate(students):
        sd = grade_data.get(s.student, {})

        grades = {
            subj["name"]: {p: sd.get(subj["name"], {}).get(p) for p in range(1, n_terms + 1)}
            for subj in subjects
        }

        annual_subj_avgs = {}
        for subj in subjects:
            vals = [sd.get(subj["name"], {}).get(p) for p in range(1, n_terms + 1)]
            valid = [v for v in vals if v is not None]
            annual_subj_avgs[subj["name"]] = round(sum(valid) / len(valid), 2) if valid else None

        avgs = [v for v in annual_subj_avgs.values() if v is not None]
        global_avg = round(sum(avgs) / len(avgs), 2) if avgs else None

        ar = result_map.get(s.student)
        if ar and ar.result:
            result = ar.result
        elif global_avg is not None:
            result = "Aprovado" if global_avg >= min_passing else "Reprovado"
        else:
            result = ""

        student_rows.append({
            "idx": idx + 1,
            "student": s.student,
            "student_name": s.student_name,
            "gender": s.gender or "",
            "grades": grades,
            "absences": attendance_data.get(s.student, {}),
            "comportamento": comportamento_data.get(s.student, {}),
            "annual_subject_avgs": annual_subj_avgs,
            "global_average": global_avg,
            "result": result,
        })

    return {
        "school_name": school_name,
        "class_group": class_group,
        "class_group_name": cg.group_name,
        "school_class": cg.school_class,
        "classroom": cg.classroom or "",
        "shift": cg.shift or "",
        "academic_year": academic_year,
        "terms": [{"name": t.name, "label": t.term_name or t.name} for t in terms],
        "subjects": subjects,
        "students": student_rows,
        "min_passing": min_passing,
    }
