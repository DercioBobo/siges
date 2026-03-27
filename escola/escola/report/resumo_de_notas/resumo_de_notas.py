import frappe
from frappe import _


def execute(filters=None):
    filters = filters or {}

    columns = [
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
            "label": _("Disciplina"),
            "fieldname": "subject",
            "fieldtype": "Link",
            "options": "Subject",
            "width": 160,
        },
        {
            "label": _("Tipo de Avaliação"),
            "fieldname": "evaluation_type",
            "fieldtype": "Data",
            "width": 140,
        },
        {
            "label": _("Nota"),
            "fieldname": "grade",
            "fieldtype": "Float",
            "width": 80,
            "precision": 1,
        },
        {
            "label": _("Data"),
            "fieldname": "evaluation_date",
            "fieldtype": "Date",
            "width": 100,
        },
        {
            "label": _("Observações"),
            "fieldname": "remarks",
            "fieldtype": "Data",
            "width": 200,
        },
    ]

    if not filters.get("class_group"):
        return columns, []

    conditions = ["ge.class_group = %(class_group)s", "ge.academic_year = %(academic_year)s"]

    if filters.get("academic_term"):
        conditions.append("ge.academic_term = %(academic_term)s")

    if filters.get("evaluation_type"):
        conditions.append("ge.evaluation_type = %(evaluation_type)s")

    where = " AND ".join(conditions)

    data = frappe.db.sql(
        f"""
        SELECT
            ger.student,
            s.full_name,
            ger.subject,
            ge.evaluation_type,
            ger.grade,
            ge.evaluation_date,
            ger.remarks
        FROM `tabGrade Entry Row` ger
        INNER JOIN `tabGrade Entry` ge ON ge.name = ger.parent
        INNER JOIN `tabStudent`     s  ON s.name  = ger.student
        WHERE {where}
        ORDER BY s.full_name, ger.subject, ge.evaluation_date
        """,
        filters,
        as_dict=True,
    )

    return columns, data
