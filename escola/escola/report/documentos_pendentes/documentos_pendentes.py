import frappe
from frappe import _


def execute(filters=None):
    filters = filters or {}

    columns = [
        {
            "label": _("Nº Aluno"),
            "fieldname": "student_code",
            "fieldtype": "Data",
            "width": 100,
        },
        {
            "label": _("Aluno"),
            "fieldname": "full_name",
            "fieldtype": "Link",
            "options": "Student",
            "width": 200,
        },
        {
            "label": _("Classe"),
            "fieldname": "school_class",
            "fieldtype": "Link",
            "options": "School Class",
            "width": 100,
        },
        {
            "label": _("Turma"),
            "fieldname": "class_group",
            "fieldtype": "Link",
            "options": "Class Group",
            "width": 130,
        },
        {
            "label": _("Documento"),
            "fieldname": "document_label",
            "fieldtype": "Data",
            "width": 200,
        },
        {
            "label": _("Obrigatório"),
            "fieldname": "is_required",
            "fieldtype": "Check",
            "width": 100,
        },
        {
            "label": _("Inscrição"),
            "fieldname": "origin_enrollment",
            "fieldtype": "Link",
            "options": "Inscricao",
            "width": 130,
        },
    ]

    conditions = ["sd.status = 'Pendente'", "s.current_status = 'Activo'"]
    values = {}

    if filters.get("school_class"):
        conditions.append("s.current_school_class = %(school_class)s")
        values["school_class"] = filters["school_class"]

    if filters.get("class_group"):
        conditions.append("s.current_class_group = %(class_group)s")
        values["class_group"] = filters["class_group"]

    if filters.get("required_only"):
        conditions.append("sd.is_required = 1")

    where = " AND ".join(conditions)

    data = frappe.db.sql(
        f"""
        SELECT
            s.student_code,
            s.full_name,
            s.current_school_class  AS school_class,
            s.current_class_group   AS class_group,
            COALESCE(td.label, sd.document_type) AS document_label,
            sd.is_required,
            sd.origin_enrollment
        FROM `tabStudent Document` sd
        JOIN `tabStudent` s ON s.name = sd.parent AND s.parenttype IS NULL
        LEFT JOIN `tabTipo de Documento` td ON td.name = sd.document_type
        WHERE {where}
        ORDER BY s.current_class_group, s.full_name, sd.document_type
        """,
        values,
        as_dict=True,
    )

    return columns, data
