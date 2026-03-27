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
            "width": 190,
        },
        {
            "label": _("Cliente"),
            "fieldname": "customer",
            "fieldtype": "Link",
            "options": "Customer",
            "width": 140,
        },
        {
            "label": _("Factura"),
            "fieldname": "invoice_name",
            "fieldtype": "Link",
            "options": "Sales Invoice",
            "width": 140,
        },
        {
            "label": _("Data"),
            "fieldname": "posting_date",
            "fieldtype": "Date",
            "width": 100,
        },
        {
            "label": _("Vencimento"),
            "fieldname": "due_date",
            "fieldtype": "Date",
            "width": 100,
        },
        {
            "label": _("Total"),
            "fieldname": "grand_total",
            "fieldtype": "Currency",
            "width": 110,
        },
        {
            "label": _("Pago"),
            "fieldname": "total_paid",
            "fieldtype": "Currency",
            "width": 110,
        },
        {
            "label": _("Pendente"),
            "fieldname": "outstanding_amount",
            "fieldtype": "Currency",
            "width": 110,
        },
        {
            "label": _("Estado"),
            "fieldname": "status",
            "fieldtype": "Data",
            "width": 100,
        },
    ]

    conditions = ["si.escola_student IS NOT NULL"]

    invoice_status = filters.get("invoice_status")
    if invoice_status == "Rascunho":
        conditions.append("si.docstatus = 0")
    elif invoice_status == "Em Aberto":
        conditions.append("si.docstatus = 1 AND si.outstanding_amount > 0")
    elif invoice_status == "Pago":
        conditions.append("si.docstatus = 1 AND si.outstanding_amount = 0")
    elif invoice_status == "Cancelado":
        conditions.append("si.docstatus = 2")
    else:
        conditions.append("si.docstatus IN (0, 1)")

    if filters.get("academic_year"):
        conditions.append("bc.academic_year = %(academic_year)s")
    if filters.get("school_class"):
        conditions.append("sfa.school_class = %(school_class)s")
    if filters.get("class_group"):
        conditions.append("sfa.class_group = %(class_group)s")
    if filters.get("student"):
        conditions.append("si.escola_student = %(student)s")

    where = " AND ".join(conditions)

    try:
        data = frappe.db.sql(
            f"""
            SELECT
                si.escola_student                                       AS student,
                s.full_name,
                si.customer,
                si.name                                                 AS invoice_name,
                si.posting_date,
                si.due_date,
                si.grand_total,
                (si.grand_total - si.outstanding_amount)                AS total_paid,
                si.outstanding_amount,
                CASE si.docstatus
                    WHEN 0 THEN 'Rascunho'
                    WHEN 1 THEN (CASE WHEN si.outstanding_amount = 0 THEN 'Pago' ELSE 'Em Aberto' END)
                    WHEN 2 THEN 'Cancelado'
                END                                                     AS status
            FROM `tabSales Invoice` si
            LEFT JOIN `tabStudent`                s   ON s.name   = si.escola_student
            LEFT JOIN `tabBilling Cycle`          bc  ON bc.name  = si.escola_billing_cycle
            LEFT JOIN `tabStudent Fee Assignment` sfa ON sfa.student = si.escola_student AND sfa.is_active = 1
            WHERE {where}
            ORDER BY s.full_name, si.posting_date DESC
            """,
            filters,
            as_dict=True,
        )
    except Exception:
        frappe.msgprint(
            _("Os campos personalizados de facturação ainda não foram criados. "
              "Execute 'bench migrate' para activar este relatório."),
            indicator="orange",
            alert=True,
        )
        return columns, []

    return columns, data
