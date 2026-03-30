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
            "label": _("Disciplinas Reprovadas"),
            "fieldname": "total_failed_subjects",
            "fieldtype": "Int",
            "width": 140,
        },
        {
            "label": _("Decisão"),
            "fieldname": "decision",
            "fieldtype": "Data",
            "width": 120,
        },
        {
            "label": _("Observações"),
            "fieldname": "remarks",
            "fieldtype": "Data",
            "width": 200,
        },
    ]

    conditions = []
    if filters.get("class_group"):
        conditions.append("sp.class_group = %(class_group)s")
    if filters.get("academic_year"):
        conditions.append("sp.academic_year = %(academic_year)s")

    where = " AND ".join(conditions) if conditions else "1=1"

    data = frappe.db.sql(
        f"""
        SELECT
            spr.student,
            s.full_name,
            spr.total_failed_subjects,
            spr.decision,
            spr.remarks
        FROM `tabStudent Promotion Row` spr
        INNER JOIN `tabStudent Promotion` sp ON sp.name = spr.parent
        INNER JOIN `tabStudent`           s  ON s.name  = spr.student
        WHERE {where}
        ORDER BY s.full_name
        """,
        filters,
        as_dict=True,
    )

    return columns, data
