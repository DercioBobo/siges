"""
Clear the open invoices of students who already left the school before
void_open_invoices_for_student() was hooked into Student Transfer and
Desistência.

For every Student with current_status Transferido or Desistente:
- Draft invoices are deleted.
- Submitted invoices with nothing paid yet are cancelled.
- Partially paid invoices are kept and logged for manual review.

Idempotent: a re-run finds nothing left to void.

Preview (read-only) before migrating:
    bench --site <site> execute escola.patches.v1_0.void_invoices_of_departed_students.preview
"""

import frappe

DEPARTED_STATUSES = ("Transferido", "Desistente")


def execute():
    from escola.escola.doctype.billing_cycle.billing_cycle import void_open_invoices_for_student

    partially_paid, errors = [], []
    deleted = cancelled = 0

    for student in _departed_students_with_open_invoices():
        result = void_open_invoices_for_student(student)
        deleted += len(result["deleted"])
        cancelled += len(result["cancelled"])
        partially_paid += [f"{student}: {inv}" for inv in result["partially_paid"]]
        errors += [f"{student}: {e}" for e in result["errors"]]
        frappe.db.commit()

    print(f"Facturas eliminadas (rascunho): {deleted}")
    print(f"Facturas canceladas (pendentes): {cancelled}")
    if partially_paid or errors:
        frappe.log_error(
            title="Escola — facturas de alunos transferidos/desistentes por rever",
            message="Parcialmente pagas (mantidas):\n{0}\n\nErros:\n{1}".format(
                "\n".join(partially_paid) or "-", "\n".join(errors) or "-"
            ),
        )
        print(f"Parcialmente pagas mantidas: {len(partially_paid)}   Erros: {len(errors)} "
              "(ver Error Log)")


def _departed_students_with_open_invoices():
    return frappe.db.sql_list(
        """
        SELECT DISTINCT s.name
        FROM `tabStudent` s
        JOIN `tabSales Invoice` si ON si.escola_student = s.name
        WHERE s.current_status IN %(statuses)s
          AND (si.docstatus = 0 OR (si.docstatus = 1 AND si.outstanding_amount > 0))
        """,
        {"statuses": DEPARTED_STATUSES},
    )


def preview():
    """Read-only: list what execute() would touch."""
    rows = frappe.db.sql(
        """
        SELECT s.name AS student, s.full_name, s.current_status,
               si.name AS invoice, si.docstatus, si.grand_total, si.outstanding_amount
        FROM `tabStudent` s
        JOIN `tabSales Invoice` si ON si.escola_student = s.name
        WHERE s.current_status IN %(statuses)s
          AND (si.docstatus = 0 OR (si.docstatus = 1 AND si.outstanding_amount > 0))
        ORDER BY s.full_name, si.posting_date
        """,
        {"statuses": DEPARTED_STATUSES},
        as_dict=True,
    )
    for r in rows:
        if r.docstatus == 0:
            action = "eliminar"
        elif r.outstanding_amount < r.grand_total:
            action = "manter (parcialmente paga)"
        else:
            action = "cancelar"
        print(f"{r.full_name} [{r.current_status}]  {r.invoice}  "
              f"total={r.grand_total} em dívida={r.outstanding_amount}  -> {action}")
    print(f"Total: {len(rows)} factura(s)")
