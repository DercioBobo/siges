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
            "label": _("Período"),
            "fieldname": "academic_term",
            "fieldtype": "Link",
            "options": "Academic Term",
            "width": 130,
        },
        {
            "label": _("MACSP"),
            "fieldname": "macsp",
            "fieldtype": "Float",
            "width": 80,
            "precision": 2,
        },
        {
            "label": _("MACS"),
            "fieldname": "macs",
            "fieldtype": "Float",
            "width": 80,
            "precision": 2,
        },
        {
            "label": _("MT"),
            "fieldname": "mt",
            "fieldtype": "Float",
            "width": 80,
            "precision": 2,
        },
        {
            "label": _("S/Nota"),
            "fieldname": "is_absent",
            "fieldtype": "Check",
            "width": 70,
        },
    ]

    conditions = ["ge.docstatus != 2"]
    if filters.get("class_group"):
        conditions.append("ge.class_group = %(class_group)s")
    if filters.get("academic_year"):
        conditions.append("ge.academic_year = %(academic_year)s")
    if filters.get("academic_term"):
        conditions.append("ge.academic_term = %(academic_term)s")
    if filters.get("subject"):
        conditions.append("ge.subject = %(subject)s")

    where = " AND ".join(conditions)

    data = frappe.db.sql(
        f"""
        SELECT
            ger.student,
            s.full_name,
            ge.subject,
            ge.academic_term,
            ger.macsp,
            ger.macs,
            ger.mt,
            ger.is_absent
        FROM `tabGrade Entry Row` ger
        INNER JOIN `tabGrade Entry` ge ON ge.name = ger.parent
        INNER JOIN `tabStudent`     s  ON s.name  = ger.student
        WHERE {where}
        ORDER BY s.full_name, ge.subject, ge.academic_term
        """,
        filters,
        as_dict=True,
    )

    return columns, data
