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
            "label": _("Nome da Avaliação"),
            "fieldname": "assessment_name",
            "fieldtype": "Data",
            "width": 150,
        },
        {
            "label": _("Nota"),
            "fieldname": "score",
            "fieldtype": "Float",
            "width": 80,
            "precision": 2,
        },
        {
            "label": _("Aprovado"),
            "fieldname": "is_approved",
            "fieldtype": "Check",
            "width": 80,
        },
        {
            "label": _("S/Nota"),
            "fieldname": "is_absent",
            "fieldtype": "Check",
            "width": 70,
        },
    ]

    conditions = []
    if filters.get("class_group"):
        conditions.append("ge.class_group = %(class_group)s")
    if filters.get("academic_year"):
        conditions.append("ge.academic_year = %(academic_year)s")
    if filters.get("academic_term"):
        conditions.append("ge.academic_term = %(academic_term)s")
    if filters.get("evaluation_type"):
        conditions.append("ge.evaluation_type = %(evaluation_type)s")

    where = " AND ".join(conditions) if conditions else "1=1"

    data = frappe.db.sql(
        f"""
        SELECT
            ger.student,
            s.full_name,
            ger.subject,
            ge.evaluation_type,
            ge.assessment_name,
            ger.score,
            ger.is_approved,
            ger.is_absent
        FROM `tabGrade Entry Row` ger
        INNER JOIN `tabGrade Entry` ge ON ge.name = ger.parent
        INNER JOIN `tabStudent`     s  ON s.name  = ger.student
        WHERE {where}
        ORDER BY s.full_name, ger.subject, ge.assessment_date, ge.creation
        """,
        filters,
        as_dict=True,
    )

    return columns, data
