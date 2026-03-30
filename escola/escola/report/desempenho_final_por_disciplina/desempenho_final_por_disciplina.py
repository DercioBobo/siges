import frappe
from frappe import _


def execute(filters=None):
    filters = filters or {}

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
            "label": _("Nota Final"),
            "fieldname": "final_grade",
            "fieldtype": "Float",
            "width": 100,
            "precision": 1,
        },
        {
            "label": _("Resultado"),
            "fieldname": "result",
            "fieldtype": "Data",
            "width": 110,
        },
    ]

    conditions = []
    if filters.get("class_group"):
        conditions.append("aa.class_group = %(class_group)s")
    if filters.get("academic_year"):
        conditions.append("aa.academic_year = %(academic_year)s")
    if filters.get("subject"):
        conditions.append("aar.subject = %(subject)s")

    where = " AND ".join(conditions) if conditions else "1=1"

    data = frappe.db.sql(
        f"""
        SELECT
            aar.subject,
            aar.student,
            s.full_name,
            aar.final_grade,
            aar.result
        FROM `tabAnnual Assessment Row` aar
        INNER JOIN `tabAnnual Assessment` aa ON aa.name = aar.parent
        INNER JOIN `tabStudent`           s  ON s.name  = aar.student
        WHERE {where}
        ORDER BY aar.subject, s.full_name
        """,
        filters,
        as_dict=True,
    )

    return columns, data
