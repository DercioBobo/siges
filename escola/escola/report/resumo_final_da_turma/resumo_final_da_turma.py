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
            "label": _("Média Final"),
            "fieldname": "overall_average",
            "fieldtype": "Float",
            "width": 100,
            "precision": 1,
        },
        {
            "label": _("Disciplinas Reprovadas"),
            "fieldname": "total_failed_subjects",
            "fieldtype": "Int",
            "width": 150,
        },
        {
            "label": _("Decisão Final"),
            "fieldname": "final_decision",
            "fieldtype": "Data",
            "width": 120,
        },
    ]

    if not filters.get("class_group") or not filters.get("academic_year"):
        return columns, []

    closure = frappe.db.get_value(
        "Academic Closure",
        {
            "class_group": filters["class_group"],
            "academic_year": filters["academic_year"],
        },
        "name",
    )
    if not closure:
        return columns, []

    rows = frappe.get_all(
        "Academic Closure Row",
        filters={"parent": closure},
        fields=["student", "overall_average", "total_failed_subjects", "final_decision"],
        order_by="student asc",
    )

    if not rows:
        return columns, []

    student_names = [r.student for r in rows]
    student_map = {
        s.name: s.full_name
        for s in frappe.get_all(
            "Student",
            filters={"name": ("in", student_names)},
            fields=["name", "full_name"],
        )
    }

    data = sorted(
        [
            {
                "student": r.student,
                "full_name": student_map.get(r.student, r.student),
                "overall_average": r.overall_average,
                "total_failed_subjects": r.total_failed_subjects,
                "final_decision": r.final_decision,
            }
            for r in rows
        ],
        key=lambda x: x["full_name"],
    )

    return columns, data
