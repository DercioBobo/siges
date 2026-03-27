import frappe
from frappe import _


def execute(filters=None):
    filters = filters or {}

    columns = [
        {
            "label": _("Ciclo"),
            "fieldname": "name",
            "fieldtype": "Link",
            "options": "Billing Cycle",
            "width": 130,
        },
        {
            "label": _("Nome do Ciclo"),
            "fieldname": "cycle_name",
            "fieldtype": "Data",
            "width": 180,
        },
        {
            "label": _("Período"),
            "fieldname": "billing_period_label",
            "fieldtype": "Data",
            "width": 150,
        },
        {
            "label": _("Modo"),
            "fieldname": "billing_mode",
            "fieldtype": "Data",
            "width": 100,
        },
        {
            "label": _("Ano Lectivo"),
            "fieldname": "academic_year",
            "fieldtype": "Link",
            "options": "Academic Year",
            "width": 120,
        },
        {
            "label": _("Classe"),
            "fieldname": "school_class",
            "fieldtype": "Link",
            "options": "School Class",
            "width": 110,
        },
        {
            "label": _("Turma"),
            "fieldname": "class_group",
            "fieldtype": "Link",
            "options": "Class Group",
            "width": 110,
        },
        {
            "label": _("Data de Facturação"),
            "fieldname": "posting_date",
            "fieldtype": "Date",
            "width": 130,
        },
        {
            "label": _("Data de Vencimento"),
            "fieldname": "due_date",
            "fieldtype": "Date",
            "width": 130,
        },
        {
            "label": _("Total Alunos"),
            "fieldname": "total_students",
            "fieldtype": "Int",
            "width": 110,
        },
        {
            "label": _("Facturas Criadas"),
            "fieldname": "total_invoices_created",
            "fieldtype": "Int",
            "width": 130,
        },
        {
            "label": _("Valor Total Facturado"),
            "fieldname": "total_amount",
            "fieldtype": "Currency",
            "width": 150,
        },
    ]

    conditions = []
    if filters.get("academic_year"):
        conditions.append("bc.academic_year = %(academic_year)s")
    if filters.get("school_class"):
        conditions.append("bc.school_class = %(school_class)s")
    if filters.get("class_group"):
        conditions.append("bc.class_group = %(class_group)s")
    if filters.get("billing_mode"):
        conditions.append("bc.billing_mode = %(billing_mode)s")

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    data = frappe.db.sql(
        f"""
        SELECT
            bc.name,
            bc.cycle_name,
            bc.billing_period_label,
            bc.billing_mode,
            bc.academic_year,
            bc.school_class,
            bc.class_group,
            bc.posting_date,
            bc.due_date,
            bc.total_students,
            bc.total_invoices_created,
            bc.total_amount
        FROM `tabBilling Cycle` bc
        {where}
        ORDER BY bc.posting_date DESC
        """,
        filters,
        as_dict=True,
    )

    return columns, data
