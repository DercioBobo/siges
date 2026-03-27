import frappe
from frappe import _


def execute(filters=None):
    filters = filters or {}

    columns = [
        {
            "label": _("Nº do Aluno"),
            "fieldname": "student_code",
            "fieldtype": "Data",
            "width": 120,
        },
        {
            "label": _("Nome Completo"),
            "fieldname": "full_name",
            "fieldtype": "Data",
            "width": 220,
        },
        {
            "label": _("Sexo"),
            "fieldname": "gender",
            "fieldtype": "Data",
            "width": 90,
        },
        {
            "label": _("Data de Nasc."),
            "fieldname": "date_of_birth",
            "fieldtype": "Date",
            "width": 110,
        },
        {
            "label": _("Encarregado"),
            "fieldname": "primary_guardian",
            "fieldtype": "Link",
            "options": "Guardian",
            "width": 180,
        },
        {
            "label": _("Estado"),
            "fieldname": "current_status",
            "fieldtype": "Data",
            "width": 110,
        },
    ]

    if not filters.get("class_group"):
        return columns, []

    assignment_filters = {
        "class_group": filters["class_group"],
        "status": "Activa",
    }
    if filters.get("academic_year"):
        assignment_filters["academic_year"] = filters["academic_year"]

    assignments = frappe.get_all(
        "Student Group Assignment",
        filters=assignment_filters,
        fields=["student"],
        order_by="student asc",
    )

    data = []
    for a in assignments:
        s = frappe.db.get_value(
            "Student",
            a.student,
            [
                "student_code",
                "full_name",
                "gender",
                "date_of_birth",
                "primary_guardian",
                "current_status",
            ],
            as_dict=True,
        )
        if s:
            data.append(s)

    return columns, data
