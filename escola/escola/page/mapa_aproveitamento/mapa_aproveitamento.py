import frappe
import json
from frappe import _


def _teacher_class_groups():
    """Return list of class group names for the current user if they are a Professor, else None."""
    user = frappe.session.user
    if "Professor" not in frappe.get_roles(user):
        return None
    teacher_name = frappe.db.get_value("Teacher", {"user_id": user}, "name")
    if not teacher_name:
        return None
    academic_year = frappe.db.get_single_value("School Settings", "current_academic_year")
    year_sql = "AND cg.academic_year = %s" if academic_year else ""

    cg_filters = {"class_teacher": teacher_name, "is_active": 1}
    if academic_year:
        cg_filters["academic_year"] = academic_year
    names = {cg.name for cg in frappe.db.get_all("Class Group", filters=cg_filters, fields=["name"])}

    params = (teacher_name, academic_year) if academic_year else (teacher_name,)
    rows = frappe.db.sql(f"""
        SELECT DISTINCT t.class_group
        FROM `tabTimetable Entry` te
        JOIN `tabTimetable` t ON t.name = te.parent
        JOIN `tabClass Group` cg ON cg.name = t.class_group
        WHERE te.teacher = %s AND t.status = 'Activo' AND cg.is_active = 1
        {year_sql}
    """, params, as_dict=True)
    names.update(r.class_group for r in rows)

    sc_params = (teacher_name, academic_year) if academic_year else (teacher_name,)
    sc_rows = frappe.db.sql(f"""
        SELECT DISTINCT cg.name
        FROM `tabSchool Class Subject` scs
        JOIN `tabClass Group` cg ON cg.school_class = scs.parent
        WHERE scs.teacher = %s AND cg.is_active = 1
        {year_sql}
    """, sc_params, as_dict=True)
    names.update(r.name for r in sc_rows)

    return list(names)


@frappe.whitelist()
def get_filter_options():
    teacher_cgs = _teacher_class_groups()
    cg_filters = {"is_active": 1}
    if teacher_cgs is not None:
        if not teacher_cgs:
            return {"class_groups": [], "terms": []}
        cg_filters["name"] = ("in", teacher_cgs)
    class_groups = frappe.get_all(
        "Class Group",
        filters=cg_filters,
        fields=["name", "group_name", "school_class", "academic_year"],
        order_by="group_name asc",
    )
    terms = frappe.get_all(
        "Academic Term",
        filters={"is_active": 1},
        fields=["name", "term_name", "academic_year", "start_date"],
        order_by="academic_year desc, start_date asc",
    )
    return {"class_groups": class_groups, "terms": terms}


def _subject_status(rows):
    if not rows:
        return "Vazio"
    score_fields = ["acsp_1", "acsp_2", "acsp_3", "acse_1", "acse_2", "acse_3", "acp"]
    has_any = any(
        r.get("is_absent") or any(r.get(f) is not None for f in score_fields)
        for r in rows
    )
    if not has_any:
        return "Vazio"
    all_done = all(r.get("is_absent") or r.get("mt") is not None for r in rows)
    return "Completo" if all_done else "Em Curso"


def _empty_row(student):
    return {
        "student": student,
        "acsp_1": None, "acsp_2": None, "acsp_3": None,
        "acse_1": None, "acse_2": None, "acse_3": None,
        "acp": None, "macsp": None, "macs": None, "mt": None,
        "is_absent": 0,
    }


@frappe.whitelist()
def get_grade_book(class_group, academic_term):
    cg = frappe.db.get_value(
        "Class Group", class_group,
        ["group_name", "school_class", "academic_year", "class_teacher"],
        as_dict=True,
    )
    if not cg:
        frappe.throw(_("Turma não encontrada."))

    term = frappe.db.get_value(
        "Academic Term", academic_term,
        ["term_name", "academic_year"],
        as_dict=True,
    )
    if not term:
        frappe.throw(_("Período não encontrado."))

    students = frappe.db.sql(
        """
        SELECT sga.student, s.full_name AS student_name, s.student_code
        FROM `tabStudent Group Assignment` sga
        JOIN `tabStudent` s ON s.name = sga.student
        WHERE sga.class_group = %s
          AND sga.academic_year = %s
          AND sga.status = 'Activa'
        ORDER BY s.full_name
        """,
        (class_group, cg.academic_year),
        as_dict=True,
    )
    student_ids = [s.student for s in students]

    subjects_out = []
    school_class = frappe.db.get_value("Class Group", class_group, "school_class")
    subj_names = []
    if school_class:
        lines = frappe.get_all(
            "School Class Subject",
            filters={"parent": school_class},
            fields=["subject"],
            order_by="idx asc",
        )
        subj_names = [l.subject for l in lines if l.subject]
    if subj_names:
            subj_infos = {
                s.name: s.subject_name
                for s in frappe.get_all(
                    "Subject",
                    filters={"name": ("in", subj_names)},
                    fields=["name", "subject_name"],
                )
            }
            # Batch lookup: one query for all Grade Entries in this class/term
            existing_ges = {
                ge.subject: ge.name
                for ge in frappe.get_all(
                    "Grade Entry",
                    filters={
                        "class_group": class_group,
                        "academic_term": academic_term,
                        "docstatus": ("!=", 2),
                    },
                    fields=["name", "subject"],
                )
            }
            for sn in subj_names:
                if sn not in subj_infos:
                    continue
                ge_name = existing_ges.get(sn)
                if ge_name:
                    db_rows = frappe.get_all(
                        "Grade Entry Row",
                        filters={"parent": ge_name},
                        fields=[
                            "student", "acsp_1", "acsp_2", "acsp_3",
                            "acse_1", "acse_2", "acse_3", "acp",
                            "macsp", "macs", "mt", "is_absent",
                        ],
                        order_by="idx asc",
                    )
                    by_student = {r.student: r for r in db_rows}
                    rows = [
                        by_student[sid] if sid in by_student else _empty_row(sid)
                        for sid in student_ids
                    ]
                else:
                    rows = [_empty_row(sid) for sid in student_ids]

                subjects_out.append({
                    "subject": sn,
                    "subject_name": subj_infos[sn],
                    "grade_entry": ge_name,
                    "status": _subject_status(rows) if ge_name else "Vazio",
                    "rows": rows,
                })

    return {
        "class_group": class_group,
        "class_group_name": cg.group_name,
        "school_class": cg.school_class,
        "academic_year": cg.academic_year,
        "academic_term": academic_term,
        "term_name": term.term_name,
        "students": [
            {"student": s.student, "student_name": s.student_name, "student_code": s.student_code}
            for s in students
        ],
        "subjects": subjects_out,
    }


def _apply_row_data(row, data):
    row.acsp_1    = data.get("acsp_1")
    row.acsp_2    = data.get("acsp_2")
    row.acsp_3    = data.get("acsp_3")
    row.acse_1    = data.get("acse_1")
    row.acse_2    = data.get("acse_2")
    row.acse_3    = data.get("acse_3")
    row.acp       = data.get("acp")
    row.is_absent = int(data.get("is_absent") or 0)


@frappe.whitelist()
def save_subject_grades(class_group, academic_term, subject, rows_json):
    rows = json.loads(rows_json) if isinstance(rows_json, str) else rows_json

    score_fields = ["acsp_1", "acsp_2", "acsp_3", "acse_1", "acse_2", "acse_3", "acp"]
    has_data = any(
        r.get("is_absent") or any(r.get(f) is not None for f in score_fields)
        for r in rows
    )
    if not has_data:
        return {"saved": False}

    student_names = {
        s.name: s.full_name
        for s in frappe.get_all(
            "Student",
            filters={"name": ("in", [r["student"] for r in rows])},
            fields=["name", "full_name"],
        )
    }

    ge_name = frappe.db.get_value(
        "Grade Entry",
        {
            "class_group": class_group,
            "academic_term": academic_term,
            "subject": subject,
            "docstatus": ("!=", 2),
        },
        "name",
    )

    if ge_name:
        doc = frappe.get_doc("Grade Entry", ge_name)
        existing = {r.student: r for r in doc.grade_rows}
        for r in rows:
            if r["student"] in existing:
                _apply_row_data(existing[r["student"]], r)
            else:
                new_row = doc.append("grade_rows", {
                    "student": r["student"],
                    "student_name": student_names.get(r["student"], ""),
                })
                _apply_row_data(new_row, r)
    else:
        cg_info = frappe.db.get_value(
            "Class Group", class_group, ["academic_year", "school_class"], as_dict=True
        ) or {}
        doc = frappe.new_doc("Grade Entry")
        doc.class_group   = class_group
        doc.academic_term = academic_term
        doc.subject       = subject
        doc.academic_year = cg_info.get("academic_year") or ""
        doc.school_class  = cg_info.get("school_class") or ""
        for r in rows:
            new_row = doc.append("grade_rows", {
                "student": r["student"],
                "student_name": student_names.get(r["student"], ""),
            })
            _apply_row_data(new_row, r)

    doc.save(ignore_permissions=True)

    saved_rows = frappe.get_all(
        "Grade Entry Row",
        filters={"parent": doc.name},
        fields=[
            "student", "acsp_1", "acsp_2", "acsp_3",
            "acse_1", "acse_2", "acse_3", "acp",
            "macsp", "macs", "mt", "is_absent",
        ],
        order_by="idx asc",
    )

    # Compute status only from the current roster to ignore stale rows of removed students
    current_student_set = {r["student"] for r in rows}
    status_rows = [sr for sr in saved_rows if sr.student in current_student_set]

    return {
        "saved": True,
        "grade_entry": doc.name,
        "status": _subject_status(status_rows),
        "rows": saved_rows,
    }
