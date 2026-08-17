"""
Shared "register a payment" action used by both the Payment Desk page and
the Sales Invoice form's "Registar Pagamento" button, so the two entry
points can never drift apart.
"""

import frappe
from frappe import _
from frappe.utils import flt, nowdate


def get_payment_account(mode_of_payment, company):
    """
    Resolve the default account for a Mode of Payment within a company.
    Shared by register_payment, Adiantamento De Pagamento and
    Renovacao De Matricula (previously duplicated identically in both).
    """
    return frappe.db.get_value(
        "Mode of Payment Account",
        {"parent": mode_of_payment, "company": company},
        "default_account",
    )


@frappe.whitelist()
def register_payment(invoice_name, mode_of_payment, amount, reference_no=None,
                      reference_date=None, waive_penalty=0):
    """
    One-click payment action:
      - optionally waives a pending multa line (draft invoices only)
      - submits the invoice if it is still a draft
      - creates and submits a Payment Entry for the given amount
      - returns a print URL for the Payment Entry (recibo)
    """
    from escola.escola.doctype.billing_cycle.penalty import _remove_penalty_lines

    inv = frappe.get_doc("Sales Invoice", invoice_name)
    if inv.docstatus == 2:
        frappe.throw(_("A factura {0} está cancelada.").format(invoice_name))

    waive_penalty = int(waive_penalty or 0)
    if waive_penalty:
        if inv.docstatus != 0:
            frappe.throw(_("Só é possível dispensar a multa numa factura em Rascunho."))
        if any(row.get("escola_is_penalty_line") for row in inv.items):
            _remove_penalty_lines(inv)
            inv.set_posting_time = 1
            inv.save(ignore_permissions=True)
            inv.reload()

    if inv.docstatus == 0:
        inv.set_posting_time = 1
        inv.submit()
        inv.reload()

    amount = flt(amount)
    if amount <= 0:
        frappe.throw(_("O valor do pagamento deve ser maior que zero."))
    if amount - flt(inv.outstanding_amount) > 0.005:
        frappe.throw(
            _("O valor ({0}) excede o saldo em dívida da factura ({1}).").format(
                frappe.format_value(amount, {"fieldtype": "Currency"}),
                frappe.format_value(inv.outstanding_amount, {"fieldtype": "Currency"}),
            )
        )

    company = frappe.db.get_single_value("School Settings", "default_company") or inv.company
    paid_to = get_payment_account(mode_of_payment, company)
    if not paid_to:
        frappe.throw(
            _("Não existe uma conta padrão configurada para o Modo de Pagamento {0} "
              "na empresa {1}. Configure-a em Modo de Pagamento > Contas.").format(
                mode_of_payment, company
            )
        )

    from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

    pe = get_payment_entry("Sales Invoice", inv.name)
    pe.mode_of_payment = mode_of_payment
    pe.paid_to = paid_to
    pe.reference_no = reference_no or ""
    pe.reference_date = reference_date or nowdate()
    pe.paid_amount = amount
    pe.received_amount = amount
    for row in pe.references:
        if row.reference_name == inv.name:
            row.allocated_amount = amount

    pe.insert(ignore_permissions=True)
    pe.submit()

    return {
        "payment_entry": pe.name,
        "sales_invoice": inv.name,
        "invoice_docstatus": inv.docstatus,
        "outstanding_amount": flt(inv.outstanding_amount) - amount,
        "print_url": f"/printview?doctype=Payment%20Entry&name={pe.name}&trigger_print=1",
    }
