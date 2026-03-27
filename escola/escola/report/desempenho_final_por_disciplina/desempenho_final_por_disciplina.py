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

    if not filters.get("class_group") or not filters.get("academic_year"):
        return columns, []

    annual = frappe.db.get_value(
        "Annual Assessment",
        {
            "class_group": filters["class_group"],
            "academic_year": filters["academic_year"],
        },
        "name",
    )
    if not annual:
        return columns, []

    row_filters = {"parent": annual}
    if filters.get("subject"):
        row_filters["subject"] = filters["subject"]

    rows = frappe.get_all(
        "Annual Assessment Row",
        filters=row_filters,
        fields=["student", "subject", "final_grade", "result"],
        order_by="subject asc, student asc",
    )

    if not rows:
        return columns, []

    student_names = list({r.student for r in rows})
    student_map = {
        s.name: s.full_name
        for s in frappe.get_all(
            "Student",
            filters={"name": ("in", student_names)},
            fields=["name", "full_name"],
        )
    }

    data = [
        {
            "subject": r.subject,
            "student": r.student,
            "full_name": student_map.get(r.student, r.student),
            "final_grade": r.final_grade,
            "result": r.result,
        }
        for r in rows
    ]

    return columns, data
