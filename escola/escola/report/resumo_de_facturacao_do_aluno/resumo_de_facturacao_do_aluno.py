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
            "label": _("Cliente"),
            "fieldname": "customer",
            "fieldtype": "Link",
            "options": "Customer",
            "width": 150,
        },
        {
            "label": _("Total Facturado"),
            "fieldname": "total_billed",
            "fieldtype": "Currency",
            "width": 130,
        },
        {
            "label": _("Total Pago"),
            "fieldname": "total_paid",
            "fieldtype": "Currency",
            "width": 120,
        },
        {
            "label": _("Saldo Pendente"),
            "fieldname": "total_outstanding",
            "fieldtype": "Currency",
            "width": 130,
        },
        {
            "label": _("Facturas em Aberto"),
            "fieldname": "open_invoices",
            "fieldtype": "Int",
            "width": 130,
        },
        {
            "label": _("Facturas Pagas"),
            "fieldname": "paid_invoices",
            "fieldtype": "Int",
            "width": 120,
        },
    ]

    conditions = ["si.escola_student IS NOT NULL", "si.docstatus != 2"]
    sfa_conditions = []

    if filters.get("academic_year"):
        conditions.append("bc.academic_year = %(academic_year)s")
    if filters.get("school_class"):
        sfa_conditions.append("sfa.school_class = %(school_class)s")
    if filters.get("class_group"):
        sfa_conditions.append("sfa.class_group = %(class_group)s")
    if filters.get("student"):
        conditions.append("si.escola_student = %(student)s")

    where_si = " AND ".join(conditions)
    where_sfa = (" AND " + " AND ".join(sfa_conditions)) if sfa_conditions else ""

    try:
        data = frappe.db.sql(
            f"""
            SELECT
                si.escola_student                                              AS student,
                s.full_name,
                MAX(si.customer)                                               AS customer,
                COALESCE(SUM(CASE WHEN si.docstatus = 1 THEN si.grand_total   ELSE 0 END), 0) AS total_billed,
                COALESCE(SUM(CASE WHEN si.docstatus = 1
                                  THEN (si.grand_total - si.outstanding_amount)
                                  ELSE 0 END), 0)                             AS total_paid,
                COALESCE(SUM(CASE WHEN si.docstatus = 1 THEN si.outstanding_amount ELSE 0 END), 0) AS total_outstanding,
                SUM(CASE WHEN si.docstatus = 1 AND si.outstanding_amount > 0  THEN 1 ELSE 0 END) AS open_invoices,
                SUM(CASE WHEN si.docstatus = 1 AND si.outstanding_amount = 0  THEN 1 ELSE 0 END) AS paid_invoices
            FROM `tabSales Invoice` si
            LEFT JOIN `tabStudent`             s   ON s.name   = si.escola_student
            LEFT JOIN `tabBilling Cycle`       bc  ON bc.name  = si.escola_billing_cycle
            LEFT JOIN `tabStudent Fee Assignment` sfa
                   ON sfa.student      = si.escola_student
                  AND sfa.is_active    = 1
                  {where_sfa}
            WHERE {where_si}
            GROUP BY si.escola_student, s.full_name
            ORDER BY s.full_name
            """,
            filters,
            as_dict=True,
        )
    except Exception:
        # Custom fields not yet created — return empty with a notice
        frappe.msgprint(
            _("Os campos personalizados de facturação ainda não foram criados. "
              "Execute 'bench migrate' para activar este relatório."),
            indicator="orange",
            alert=True,
        )
        return columns, []

    return columns, data
