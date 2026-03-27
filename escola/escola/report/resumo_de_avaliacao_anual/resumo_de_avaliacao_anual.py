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
            "label": _("Nota Final"),
            "fieldname": "final_grade",
            "fieldtype": "Float",
            "width": 90,
            "precision": 1,
        },
        {
            "label": _("Resultado"),
            "fieldname": "result",
            "fieldtype": "Data",
            "width": 100,
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

    annual_assessment = frappe.db.get_value(
        "Annual Assessment",
        {
            "class_group": filters["class_group"],
            "academic_year": filters["academic_year"],
        },
        "name",
    )

    if not annual_assessment:
        return columns, []

    rows = frappe.get_all(
        "Annual Assessment Row",
        filters={"parent": annual_assessment},
        fields=["student", "subject", "final_grade", "result", "remarks"],
        order_by="student asc, subject asc",
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
                "subject": r.subject,
                "final_grade": r.final_grade,
                "result": r.result,
                "remarks": r.remarks,
            }
        )

    data.sort(key=lambda x: (x["full_name"], x["subject"]))

    return columns, data
