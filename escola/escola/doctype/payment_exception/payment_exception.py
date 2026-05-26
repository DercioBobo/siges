import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, today


class PaymentException(Document):
    def validate(self):
        if self.billing_date and self.extended_due_date:
            if getdate(self.extended_due_date) <= getdate(self.billing_date):
                frappe.throw(
                    _("A Nova Data de Vencimento deve ser posterior à Data de Facturação."),
                    title=_("Data inválida"),
                )
        if self.is_active:
            self._validate_unique_billing_date()

    def on_update(self):
        if self.is_active:
            self._apply_to_existing_cycles()

    def _validate_unique_billing_date(self):
        """Only one active exception per billing date."""
        existing = frappe.db.sql(
            """
            SELECT name FROM `tabPayment Exception`
            WHERE is_active = 1 AND name != %s AND billing_date = %s
            LIMIT 1
            """,
            (self.name or "", self.billing_date),
        )
        if existing:
            frappe.throw(
                _("Já existe uma Excepção de Pagamento activa para a data de facturação "
                  "<b>{0}</b>: <b>{1}</b>.").format(
                    frappe.format(self.billing_date, {"fieldtype": "Date"}),
                    existing[0][0],
                ),
                title=_("Data de facturação duplicada"),
            )

    def _apply_to_existing_cycles(self):
        """
        Push extended_due_date to all non-cancelled cycles whose posting_date
        matches billing_date, and update due_date on their invoices.
        """
        cycles = frappe.get_all(
            "Billing Cycle",
            filters={
                "posting_date": self.billing_date,
                "status": ("!=", "Cancelado"),
            },
            pluck="name",
        )
        if not cycles:
            return

        penalties_flag = int(self.disable_penalties or 0)
        for cycle_name in cycles:
            frappe.db.set_value(
                "Billing Cycle", cycle_name,
                {
                    "penalties_disabled": penalties_flag,
                    "exception_ref": self.name,
                },
                update_modified=False,
            )

        frappe.db.sql(
            """
            UPDATE `tabSales Invoice`
            SET due_date = %s
            WHERE escola_billing_cycle IN %s AND docstatus = 0
            """,
            (self.extended_due_date, tuple(cycles)),
        )

        inv_count = frappe.db.sql("SELECT ROW_COUNT()")[0][0]

        frappe.msgprint(
            _("{0} ciclo(s) e {1} factura(s) actualizados com vencimento <b>{2}</b>.").format(
                len(cycles),
                inv_count,
                frappe.format(self.extended_due_date, {"fieldtype": "Date"}),
            ),
            title=_("Excepção aplicada"),
            indicator="green",
        )


def get_active_exception(for_date=None):
    """Return the active Payment Exception for the given billing date, or None."""
    check_date = for_date or getdate(today())
    rows = frappe.get_all(
        "Payment Exception",
        filters={
            "is_active": 1,
            "billing_date": check_date,
        },
        fields=["name", "extended_due_date", "disable_penalties", "reason"],
        limit=1,
    )
    return rows[0] if rows else None
