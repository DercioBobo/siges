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
    if waive_penalty and inv.docstatus == 1:
        # Submitted lines can't be edited — write the multa off instead.
        waive_submitted_penalty(inv.name)
        inv.reload()
        if flt(inv.outstanding_amount) <= 0:
            # Only the multa was left: nothing to pay, no recibo.
            return {
                "payment_entry": None,
                "sales_invoice": inv.name,
                "invoice_docstatus": inv.docstatus,
                "outstanding_amount": 0,
                "print_url": None,
            }
    elif waive_penalty:
        if any(row.get("escola_is_penalty_line") for row in inv.items):
            _remove_penalty_lines(inv)
            inv.set_posting_time = 1
            inv.save(ignore_permissions=True)
            inv.reload()
            # Never submit with the multa still on it — the payment below would
            # then leave exactly the multa as outstanding on a submitted invoice.
            if any(row.get("escola_is_penalty_line") for row in inv.items):
                frappe.throw(_("Não foi possível remover a multa da factura {0}.").format(inv.name))

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


# ---------------------------------------------------------------------------
# Waive the multa of a SUBMITTED invoice — no Credit Note
# ---------------------------------------------------------------------------
# A submitted invoice's lines can't change, so the multa is written off with a
# Journal Entry against the invoice: debit the multa's income account (and any
# tax charged on it, proportionally), credit the customer's receivable with
# reference to the invoice. ERPNext then lowers the invoice's outstanding_amount.

WAIVER_REMARK = "Dispensa de multa"


def _already_waived(inv):
    return flt(frappe.db.sql(
        """
        SELECT COALESCE(SUM(jea.credit_in_account_currency), 0)
        FROM `tabJournal Entry Account` jea
        JOIN `tabJournal Entry` je ON je.name = jea.parent
        WHERE je.docstatus = 1
          AND je.user_remark LIKE %s
          AND jea.reference_type = 'Sales Invoice'
          AND jea.reference_name = %s
        """,
        (f"{WAIVER_REMARK}%", inv.name),
    )[0][0])


@frappe.whitelist()
def waive_submitted_penalty(invoice_name):
    """
    Write off the multa still owed on a submitted invoice. Idempotent: never
    waives more than the multa lines minus what was already waived, nor more
    than the outstanding amount. Returns the Journal Entry name or None.
    """
    inv = frappe.get_doc("Sales Invoice", invoice_name)
    if inv.docstatus != 1:
        frappe.throw(_("A factura {0} não está submetida.").format(inv.name))

    penalty_rows = [r for r in inv.items if r.get("escola_is_penalty_line")]
    penalty_net = sum(flt(r.net_amount or r.amount) for r in penalty_rows)
    outstanding = flt(inv.outstanding_amount)
    if not penalty_rows or penalty_net <= 0 or outstanding <= 0:
        return None

    # Tax charged on the multa, proportionally per tax row
    ratio = penalty_net / flt(inv.net_total) if flt(inv.net_total) else 0
    tax_lines = []
    for t in inv.get("taxes") or []:
        share = round(flt(t.base_tax_amount_after_discount_amount or t.tax_amount) * ratio, 2)
        if share:
            tax_lines.append((t.account_head, share, t.cost_center))

    gross = round(penalty_net + sum(s for _a, s, _c in tax_lines), 2)
    remaining = round(gross - _already_waived(inv), 2)
    if remaining <= 0:
        return None

    amount = min(remaining, outstanding)
    # Rounding (rounded_total) can leave a few cents — absorb them.
    if 0 < outstanding - amount < 1:
        amount = outstanding

    # Reverse the tax on the multa only when waiving it in full; whatever is
    # left goes to the multa's income account.
    debits = list(tax_lines) if amount >= gross else []
    income = round(amount - sum(v for _a, v, _c in debits), 2)
    debits.append((penalty_rows[0].income_account, income, penalty_rows[0].cost_center))

    je = frappe.new_doc("Journal Entry")
    je.voucher_type = "Write Off Entry"
    je.company = inv.company
    je.posting_date = nowdate()
    je.user_remark = f"{WAIVER_REMARK} — {inv.name}"
    for acc, value, cc in debits:
        if value:
            je.append("accounts", {
                "account": acc,
                "debit_in_account_currency": value,
                "cost_center": cc or inv.cost_center,
            })
    je.append("accounts", {
        "account": inv.debit_to,
        "party_type": "Customer",
        "party": inv.customer,
        "credit_in_account_currency": amount,
        "reference_type": "Sales Invoice",
        "reference_name": inv.name,
        "cost_center": inv.cost_center,
    })
    je.insert(ignore_permissions=True)
    je.submit()
    return je.name


def _invoices_with_unpaid_penalty_only():
    """Submitted invoices whose outstanding is exactly what's left of the multa."""
    return frappe.db.sql(
        """
        SELECT si.name, si.escola_student, si.grand_total, si.outstanding_amount,
               SUM(sii.amount) AS multa
        FROM `tabSales Invoice` si
        JOIN `tabSales Invoice Item` sii
          ON sii.parent = si.name AND sii.escola_is_penalty_line = 1
        WHERE si.docstatus = 1 AND si.outstanding_amount > 0
        GROUP BY si.name
        HAVING si.outstanding_amount <= SUM(sii.amount) + 1
        ORDER BY si.posting_date
        """,
        as_dict=True,
    )


def preview_fix_unpaid_penalties():
    """
    Read-only. bench --site <site> execute escola.escola.payment_actions.preview_fix_unpaid_penalties
    """
    rows = _invoices_with_unpaid_penalty_only()
    for r in rows:
        print(f"{r.name}  aluno={r.escola_student}  total={r.grand_total}  "
              f"em dívida={r.outstanding_amount}  multa={r.multa}")
    print(f"Total: {len(rows)} factura(s), "
          f"{sum(flt(r.outstanding_amount) for r in rows):.2f} a dispensar")


def fix_unpaid_penalties():
    """
    Waive the leftover multa on every invoice where the multa is all that's
    still owed (the fee itself was paid).
    bench --site <site> execute escola.escola.payment_actions.fix_unpaid_penalties
    """
    from escola.escola.doctype.billing_cycle.penalty import update_student_financial_status

    done, errors, students = [], [], set()
    for r in _invoices_with_unpaid_penalty_only():
        try:
            frappe.db.savepoint("waive_penalty")
            je = waive_submitted_penalty(r.name)
            if je:
                done.append(f"{r.name} -> {je}")
                students.add(r.escola_student)
            frappe.db.commit()
        except Exception as e:
            frappe.db.rollback(save_point="waive_penalty")
            errors.append(f"{r.name}: {e}")

    for s in filter(None, students):
        try:
            update_student_financial_status(s)
        except Exception:
            pass

    print("\n".join(done))
    print(f"Dispensadas: {len(done)}   Erros: {len(errors)}")
    if errors:
        print("\n".join(errors))
        frappe.log_error(title="Escola — erro ao dispensar multas", message="\n".join(errors))
