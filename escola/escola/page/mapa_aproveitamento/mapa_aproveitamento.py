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
    score_fields = ["acsp_1", "acsp_2", "acse_1", "acse_2", "acp"]
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
        "acsp_1": None, "acsp_2": None,
        "acse_1": None, "acse_2": None,
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
            order_by="sort_order asc, idx asc",
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
                            "student", "acsp_1", "acsp_2",
                            "acse_1", "acse_2", "acp",
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
    row.acse_1    = data.get("acse_1")
    row.acse_2    = data.get("acse_2")
    row.acp       = data.get("acp")
    if "is_absent" in data:
        row.is_absent = int(data.get("is_absent") or 0)


@frappe.whitelist()
def save_subject_grades(class_group, academic_term, subject, rows_json):
    rows = json.loads(rows_json) if isinstance(rows_json, str) else rows_json

    score_fields = ["acsp_1", "acsp_2", "acse_1", "acse_2", "acp"]
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
            "student", "acsp_1", "acsp_2",
            "acse_1", "acse_2", "acp",
            "macsp", "macs", "mt", "is_absent",
        ],
        order_by="idx asc",
    )

    current_student_set = {r["student"] for r in rows}
    status_rows = [sr for sr in saved_rows if sr.student in current_student_set]

    return {
        "saved": True,
        "grade_entry": doc.name,
        "status": _subject_status(status_rows),
        "rows": saved_rows,
    }


@frappe.whitelist()
def get_annual_grade_book(class_group, academic_year):
    cg = frappe.db.get_value(
        "Class Group", class_group,
        ["group_name", "school_class", "academic_year"],
        as_dict=True,
    )
    if not cg:
        frappe.throw(_("Turma não encontrada."))

    terms = frappe.get_all(
        "Academic Term",
        filters={"academic_year": academic_year, "is_active": 1},
        fields=["name", "term_name", "start_date"],
        order_by="start_date asc",
    )

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
        (class_group, academic_year),
        as_dict=True,
    )
    student_ids = [s.student for s in students]

    school_class = cg.school_class
    subj_names = []
    if school_class:
        lines = frappe.get_all(
            "School Class Subject",
            filters={"parent": school_class},
            fields=["subject"],
            order_by="sort_order asc, idx asc",
        )
        subj_names = [l.subject for l in lines if l.subject]

    subjects_out = []
    if subj_names:
        subj_infos = {
            s.name: s.subject_name
            for s in frappe.get_all(
                "Subject",
                filters={"name": ("in", subj_names)},
                fields=["name", "subject_name"],
            )
        }

        term_names = [t.name for t in terms]
        all_ges = frappe.get_all(
            "Grade Entry",
            filters={
                "class_group": class_group,
                "academic_term": ("in", term_names) if term_names else ["__never__"],
                "docstatus": ("!=", 2),
            },
            fields=["name", "subject", "academic_term"],
        ) if term_names else []

        # subject → term → ge_name
        ge_map = {}
        for ge in all_ges:
            ge_map.setdefault(ge.subject, {})[ge.academic_term] = ge.name

        # Batch-fetch all rows
        ge_names = [ge.name for ge in all_ges]
        rows_by_ge = {}
        if ge_names:
            all_rows = frappe.db.sql("""
                SELECT ger.parent, ger.student,
                       ger.acsp_1, ger.acsp_2,
                       ger.acse_1, ger.acse_2,
                       ger.acp, ger.macsp, ger.macs, ger.mt, ger.is_absent
                FROM `tabGrade Entry Row` ger
                WHERE ger.parent IN ({})
            """.format(",".join(["%s"] * len(ge_names))), ge_names, as_dict=True)
            for r in all_rows:
                rows_by_ge.setdefault(r.parent, {})[r.student] = r

        for sn in subj_names:
            if sn not in subj_infos:
                continue

            subj_rows = []
            for sid in student_ids:
                term_entries = []
                for term in terms:
                    ge_name = ge_map.get(sn, {}).get(term.name)
                    td = (rows_by_ge.get(ge_name) or {}).get(sid) or {}
                    term_entries.append({
                        "acsp_1":  td.get("acsp_1"),
                        "acsp_2":  td.get("acsp_2"),
                        "macsp":   td.get("macsp"),
                        "acse_1":  td.get("acse_1"),
                        "acse_2":  td.get("acse_2"),
                        "macs":    td.get("macs"),
                        "acp":     td.get("acp"),
                        "mt":      td.get("mt"),
                        "is_absent": int(td.get("is_absent") or 0),
                    })

                mt_vals = [t["mt"] for t in term_entries if t["mt"] is not None and not t["is_absent"]]
                mf = round(sum(mt_vals) / len(mt_vals)) if mt_vals else None

                subj_rows.append({
                    "student": sid,
                    "terms": term_entries,
                    "mf": mf,
                })

            subjects_out.append({
                "subject": sn,
                "subject_name": subj_infos[sn],
                "rows": subj_rows,
            })

    return {
        "class_group": class_group,
        "class_group_name": cg.group_name,
        "academic_year": academic_year,
        "terms": [{"name": t.name, "term_name": t.term_name or t.name} for t in terms],
        "students": [
            {"student": s.student, "student_name": s.student_name}
            for s in students
        ],
        "subjects": subjects_out,
    }
