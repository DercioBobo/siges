import frappe
import json
from frappe import _


@frappe.whitelist()
def get_filter_options():
    class_groups = frappe.get_all(
        "Class Group",
        filters={"is_active": 1},
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

    curriculum = frappe.db.get_value(
        "Class Curriculum",
        {"class_group": class_group, "is_active": 1},
        "name",
    )

    subjects_out = []
    if curriculum:
        lines = frappe.get_all(
            "Class Curriculum Line",
            filters={"parent": curriculum},
            fields=["subject"],
            order_by="idx asc",
        )
        subj_names = [l.subject for l in lines if l.subject]
        if subj_names:
            subj_infos = {
                s.name: s.subject_name
                for s in frappe.get_all(
                    "Subject",
                    filters={"name": ("in", subj_names), "disabled": 0},
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
