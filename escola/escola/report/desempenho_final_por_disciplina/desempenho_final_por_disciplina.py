import frappe
from frappe import _


def execute(filters=None):
    filters = filters or {}

    min_passing = float(
        frappe.db.get_single_value("School Settings", "minimum_passing_grade") or 10
    )

    columns = [
        {
            "label": _("Disciplina"),
            "fieldname": "subject",
            "fieldtype": "Link",
            "options": "Subject",
            "width": 160,
        },
        {
            "label": _("Aluno"),
            "fieldname": "student",
            "fieldtype": "Link",
            "options": "Student",
            "width": 130,
        },
        {
            "label": _("Nome Completo"),
            "fieldname": "full_name",
            "fieldtype": "Data",
            "width": 210,
        },
        {
            "label": _("Média Anual"),
            "fieldname": "annual_avg",
            "fieldtype": "Float",
            "width": 100,
            "precision": 2,
        },
        {
            "label": _("Resultado"),
            "fieldname": "result",
            "fieldtype": "Data",
            "width": 110,
        },
    ]

    conditions = ["ge.docstatus != 2", "ger.is_absent = 0", "ger.mt IS NOT NULL"]
    if filters.get("class_group"):
        conditions.append("ge.class_group = %(class_group)s")
    if filters.get("academic_year"):
        conditions.append("ge.academic_year = %(academic_year)s")
    if filters.get("subject"):
        conditions.append("ge.subject = %(subject)s")

    where = " AND ".join(conditions)

    rows = frappe.db.sql(
        f"""
        SELECT
            ge.subject,
            ger.student,
            s.full_name,
            ROUND(AVG(ger.mt), 2) AS annual_avg
        FROM `tabGrade Entry Row` ger
        INNER JOIN `tabGrade Entry` ge ON ge.name = ger.parent
        INNER JOIN `tabStudent`     s  ON s.name  = ger.student
        WHERE {where}
        GROUP BY ge.subject, ger.student, s.full_name
        ORDER BY ge.subject, s.full_name
        """,
        filters,
        as_dict=True,
    )

    for r in rows:
        avg = float(r.annual_avg) if r.annual_avg is not None else None
        r["result"] = ("Aprovado" if avg >= min_passing else "Reprovado") if avg is not None else "—"

    return columns, rows
