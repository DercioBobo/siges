"""
One-off clean-up of monthly-fee invoices left open while the school was
still adopting the system (payments received but never registered).

Targets Billing Cycle invoices posted in the given months that have nothing
paid, for students who DID pay (fully or partially) at least one other
Billing Cycle invoice — proof they are up to date and the old invoice simply
wasn't marked. Students with no payment at all are left alone: they may
really owe.

- Draft invoices are deleted.
- Submitted invoices with nothing paid are cancelled.
- Partially paid invoices are kept and listed for manual review.

Preview (read-only) first:
    bench --site <site> execute escola.escola.invoice_cleanup.preview
Then:
    bench --site <site> execute escola.escola.invoice_cleanup.execute

Defaults to June and July 2026; other periods via
    --kwargs "{'year': 2026, 'months': [6, 7]}"
"""

import frappe
from frappe import _
from frappe.utils import flt

DEFAULT_YEAR = 2026
DEFAULT_MONTHS = (6, 7)


def _candidates(year, months):
    return frappe.db.sql(
        """
        SELECT si.name, si.docstatus, si.escola_student, st.full_name,
               si.posting_date, si.grand_total, si.outstanding_amount,
               (
                   SELECT paid.name FROM `tabSales Invoice` paid
                   WHERE paid.escola_student = si.escola_student
                     AND paid.name != si.name
                     AND paid.docstatus = 1
                     AND IFNULL(paid.escola_billing_cycle, '') != ''
                     AND paid.outstanding_amount < paid.grand_total
                   ORDER BY paid.posting_date DESC
                   LIMIT 1
               ) AS paid_evidence
        FROM `tabSales Invoice` si
        LEFT JOIN `tabStudent` st ON st.name = si.escola_student
        WHERE si.docstatus IN (0, 1)
          AND IFNULL(si.escola_billing_cycle, '') != ''
          AND IFNULL(si.escola_student, '') != ''
          AND YEAR(si.posting_date) = %(year)s
          AND MONTH(si.posting_date) IN %(months)s
          AND (si.docstatus = 0 OR si.outstanding_amount > 0)
        ORDER BY st.full_name, si.posting_date
        """,
        {"year": int(year), "months": tuple(int(m) for m in months)},
        as_dict=True,
    )


def _action(r):
    if not r.paid_evidence:
        return "manter (aluno sem nenhum pagamento)"
    if r.docstatus == 0:
        return "eliminar"
    if flt(r.outstanding_amount) < flt(r.grand_total):
        return "manter (parcialmente paga)"
    return "cancelar"


def preview(year=DEFAULT_YEAR, months=DEFAULT_MONTHS):
    """Read-only: list every candidate invoice and what execute() would do."""
    counts = {}
    for r in _candidates(year, months):
        action = _action(r)
        counts[action] = counts.get(action, 0) + 1
        print(f"{r.full_name or r.escola_student} ({r.escola_student})  {r.name}  "
              f"{r.posting_date}  total={r.grand_total}  em dívida={r.outstanding_amount}  "
              f"pagou={r.paid_evidence or '-'}  -> {action}")
    print("-" * 60)
    for action, n in sorted(counts.items()):
        print(f"{action}: {n}")


def execute(year=DEFAULT_YEAR, months=DEFAULT_MONTHS):
    from escola.escola.doctype.billing_cycle.billing_cycle import _unlink_from_generation_log
    from escola.escola.doctype.billing_cycle.penalty import update_student_financial_status

    deleted, cancelled, kept, errors = [], [], [], []
    students = set()
    note = _("Factura eliminada — limpeza de facturas já pagas (período de implementação).")

    for r in _candidates(year, months):
        action = _action(r)
        if action not in ("eliminar", "cancelar"):
            kept.append(f"{r.name}: {action}")
            continue
        try:
            frappe.db.savepoint("invoice_cleanup")
            if action == "cancelar":
                frappe.get_doc("Sales Invoice", r.name).cancel()
                cancelled.append(r.name)
            else:
                _unlink_from_generation_log(r.name, note)
                frappe.delete_doc("Sales Invoice", r.name, ignore_permissions=True)
                deleted.append(r.name)
            students.add(r.escola_student)
            frappe.db.commit()
        except Exception as e:
            frappe.db.rollback(save_point="invoice_cleanup")
            errors.append(f"{r.name}: {e}")

    for s in students:
        try:
            update_student_financial_status(s)
        except Exception:
            pass

    print(f"Eliminadas (rascunho): {len(deleted)}")
    print(f"Canceladas: {len(cancelled)}")
    print(f"Mantidas: {len(kept)}")
    print(f"Erros: {len(errors)}")
    if errors:
        print("\n".join(errors))
        frappe.log_error(title="Escola — erro na limpeza de facturas", message="\n".join(errors))


# ---------------------------------------------------------------------------
# Duplicate monthly invoices — keep the newest, remove the older ones
# ---------------------------------------------------------------------------
# A duplicate is two or more regular (non-"Extras Mensais") Billing Cycle
# invoices for the same student posted within the date range. The newest
# (by creation) is kept. An older copy with any payment on it is never
# touched — it's listed so you can decide by hand.
#
#   bench --site <site> execute escola.escola.invoice_cleanup.preview_duplicates
#   bench --site <site> execute escola.escola.invoice_cleanup.execute_duplicates
# Defaults to posting dates 10–30 July 2026; otherwise
#   --kwargs "{'from_date': '2026-08-10', 'to_date': '2026-08-30'}"

DUP_FROM, DUP_TO = "2026-07-10", "2026-07-30"


def _duplicate_groups(from_date, to_date):
    rows = frappe.db.sql(
        """
        SELECT si.name, si.docstatus, si.escola_student, st.full_name, si.creation,
               si.posting_date, si.due_date, si.grand_total, si.outstanding_amount,
               si.escola_billing_cycle
        FROM `tabSales Invoice` si
        LEFT JOIN `tabStudent` st ON st.name = si.escola_student
        WHERE si.docstatus IN (0, 1)
          AND IFNULL(si.escola_billing_cycle, '') != ''
          AND IFNULL(si.escola_student, '') != ''
          AND COALESCE(si.escola_is_addon_invoice, 0) = 0
          AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
        ORDER BY st.full_name, si.escola_student, si.creation DESC
        """,
        {"from_date": from_date, "to_date": to_date},
        as_dict=True,
    )
    groups = {}
    for r in rows:
        groups.setdefault(r.escola_student, []).append(r)
    # newest first within each group (ORDER BY creation DESC)
    return [g for g in groups.values() if len(g) > 1]


def _has_payment(r):
    return r.docstatus == 1 and flt(r.outstanding_amount) < flt(r.grand_total)


def _duplicate_action(r):
    if _has_payment(r):
        return "manter (tem pagamento — rever)"
    return "eliminar" if r.docstatus == 0 else "cancelar"


def _describe(r):
    paid = flt(r.grand_total) - flt(r.outstanding_amount) if r.docstatus == 1 else 0
    state = "rascunho" if r.docstatus == 0 else f"submetida, pago={paid:.2f}"
    return (f"{r.name}  criada={r.creation:%Y-%m-%d %H:%M}  emissão={r.posting_date}  "
            f"total={r.grand_total}  ({state})  ciclo={r.escola_billing_cycle}")


def preview_duplicates(from_date=DUP_FROM, to_date=DUP_TO):
    """Read-only: list each student's duplicates and what would happen."""
    counts = {}
    groups = _duplicate_groups(from_date, to_date)
    for g in groups:
        keep, older = g[0], g[1:]
        print(f"\n{keep.full_name or keep.escola_student} ({keep.escola_student})")
        print(f"   MANTER    {_describe(keep)}")
        for r in older:
            action = _duplicate_action(r)
            counts[action] = counts.get(action, 0) + 1
            print(f"   {action.upper():<9} {_describe(r)}")
        if not _has_payment(keep) and any(_has_payment(r) for r in older):
            print("   ! a factura mais antiga tem pagamento e a mais recente não — "
                  "talvez seja a recente que deve sair")
    print("-" * 60)
    print(f"Alunos com duplicados: {len(groups)}")
    for action, n in sorted(counts.items()):
        print(f"{action}: {n}")


def execute_duplicates(from_date=DUP_FROM, to_date=DUP_TO):
    from escola.escola.doctype.billing_cycle.billing_cycle import _unlink_from_generation_log
    from escola.escola.doctype.billing_cycle.penalty import update_student_financial_status

    deleted, cancelled, kept, errors = [], [], [], []
    students = set()
    note = _("Factura eliminada — duplicada (mantida a mais recente).")

    for g in _duplicate_groups(from_date, to_date):
        for r in g[1:]:
            action = _duplicate_action(r)
            if action not in ("eliminar", "cancelar"):
                kept.append(f"{r.name}: {action}")
                continue
            try:
                frappe.db.savepoint("dup_cleanup")
                if action == "cancelar":
                    frappe.get_doc("Sales Invoice", r.name).cancel()
                    cancelled.append(r.name)
                else:
                    _unlink_from_generation_log(r.name, note)
                    frappe.delete_doc("Sales Invoice", r.name, ignore_permissions=True)
                    deleted.append(r.name)
                students.add(r.escola_student)
                frappe.db.commit()
            except Exception as e:
                frappe.db.rollback(save_point="dup_cleanup")
                errors.append(f"{r.name}: {e}")

    for s in students:
        try:
            update_student_financial_status(s)
        except Exception:
            pass

    print(f"Eliminadas (rascunho): {len(deleted)}")
    print(f"Canceladas: {len(cancelled)}")
    print(f"Mantidas (com pagamento): {len(kept)}")
    if kept:
        print("\n".join(kept))
    print(f"Erros: {len(errors)}")
    if errors:
        print("\n".join(errors))
        frappe.log_error(title="Escola — erro ao remover facturas duplicadas", message="\n".join(errors))
