import frappe
from frappe import _


def execute(filters=None):
    filters = filters or {}

    columns = [
        {
            "label": _("Renovação"),
            "fieldname": "name",
            "fieldtype": "Link",
            "options": "Renovacao De Matricula",
            "width": 130,
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
            "label": _("Ano de Origem"),
            "fieldname": "academic_year",
            "fieldtype": "Link",
            "options": "Academic Year",
            "width": 120,
        },
        {
            "label": _("Ano de Renovação"),
            "fieldname": "target_academic_year",
            "fieldtype": "Link",
            "options": "Academic Year",
            "width": 120,
        },
        {
            "label": _("Data de Renovação"),
            "fieldname": "renewal_date",
            "fieldtype": "Date",
            "width": 120,
        },
        {
            "label": _("Estado"),
            "fieldname": "status",
            "fieldtype": "Data",
            "width": 100,
        },
        {
            "label": _("Factura"),
            "fieldname": "sales_invoice",
            "fieldtype": "Link",
            "options": "Sales Invoice",
            "width": 130,
        },
    ]

    conditions = ["r.docstatus != 2"]  # exclude cancelled

    if filters.get("academic_year"):
        conditions.append("r.academic_year = %(academic_year)s")
    if filters.get("target_academic_year"):
        conditions.append("r.target_academic_year = %(target_academic_year)s")
    if filters.get("from_date"):
        conditions.append("r.renewal_date >= %(from_date)s")
    if filters.get("to_date"):
        conditions.append("r.renewal_date <= %(to_date)s")

    where = " AND ".join(conditions)

    data = frappe.db.sql(
        f"""
        SELECT
            r.name,
            r.student,
            s.full_name,
            r.academic_year,
            r.target_academic_year,
            r.renewal_date,
            CASE r.docstatus
                WHEN 0 THEN 'Rascunho'
                WHEN 1 THEN 'Confirmada'
                ELSE 'Cancelada'
            END AS status,
            r.sales_invoice
        FROM `tabRenovacao De Matricula` r
        LEFT JOIN `tabStudent` s ON s.name = r.student
        WHERE {where}
        ORDER BY r.renewal_date DESC, s.full_name ASC
        """,
        filters,
        as_dict=True,
    )

    return columns, data
