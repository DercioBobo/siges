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
            "width": 200,
        },
        {
            "label": _("Classe"),
            "fieldname": "school_class",
            "fieldtype": "Link",
            "options": "School Class",
            "width": 120,
        },
        {
            "label": _("Turma"),
            "fieldname": "class_group",
            "fieldtype": "Link",
            "options": "Class Group",
            "width": 120,
        },
        {
            "label": _("Média Final"),
            "fieldname": "overall_average",
            "fieldtype": "Float",
            "width": 100,
            "precision": 1,
        },
        {
            "label": _("Total Disciplinas"),
            "fieldname": "total_subjects",
            "fieldtype": "Int",
            "width": 120,
        },
        {
            "label": _("Aprovadas"),
            "fieldname": "passed_subjects",
            "fieldtype": "Int",
            "width": 100,
        },
        {
            "label": _("Reprovadas"),
            "fieldname": "failed_subjects",
            "fieldtype": "Int",
            "width": 100,
        },
        {
            "label": _("Decisão Final"),
            "fieldname": "final_decision",
            "fieldtype": "Data",
            "width": 120,
        },
    ]

    conditions = []
    if filters.get("academic_year"):
        conditions.append("rc.academic_year = %(academic_year)s")
    if filters.get("school_class"):
        conditions.append("rc.school_class = %(school_class)s")
    if filters.get("class_group"):
        conditions.append("rc.class_group = %(class_group)s")
    if filters.get("final_decision"):
        conditions.append("rc.final_decision = %(final_decision)s")

    where = " AND ".join(conditions) if conditions else "1=1"

    data = frappe.db.sql(
        f"""
        SELECT
            rc.student,
            s.full_name,
            rc.school_class,
            rc.class_group,
            rc.overall_average,
            rc.total_subjects,
            rc.passed_subjects,
            rc.failed_subjects,
            rc.final_decision
        FROM `tabReport Card` rc
        INNER JOIN `tabStudent` s ON s.name = rc.student
        WHERE {where}
        ORDER BY s.full_name
        """,
        filters,
        as_dict=True,
    )

    return columns, data
