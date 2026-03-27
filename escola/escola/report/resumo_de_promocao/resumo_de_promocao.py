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

    if not filters.get("class_group") or not filters.get("academic_year"):
        return columns, []

    promotion = frappe.db.get_value(
        "Student Promotion",
        {
            "class_group": filters["class_group"],
            "academic_year": filters["academic_year"],
        },
        "name",
    )

    if not promotion:
        return columns, []

    rows = frappe.get_all(
        "Student Promotion Row",
        filters={"parent": promotion},
        fields=["student", "total_failed_subjects", "decision", "remarks"],
        order_by="student asc",
    )

    if not rows:
        return columns, []

    student_names = list({r.student for r in rows})
    student_map = {}
    for name in student_names:
        full_name = frappe.db.get_value("Student", name, "full_name")
        student_map[name] = full_name or name

    data = []
    for r in rows:
        data.append(
            {
                "student": r.student,
                "full_name": student_map.get(r.student, r.student),
                "total_failed_subjects": r.total_failed_subjects,
                "decision": r.decision,
                "remarks": r.remarks,
            }
        )

    data.sort(key=lambda x: x["full_name"])

    return columns, data
