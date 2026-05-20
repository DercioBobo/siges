import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, today


class PaymentException(Document):
    def validate(self):
        if self.applies_from and self.applies_until:
            if getdate(self.applies_until) < getdate(self.applies_from):
                frappe.throw(
                    _("A data «Válida até» não pode ser anterior a «Válida de»."),
                    title=_("Período inválido"),
                )
        if self.extended_due_date and self.applies_from:
            if getdate(self.extended_due_date) < getdate(self.applies_from):
                frappe.throw(
                    _("A Nova Data de Vencimento não pode ser anterior ao início do período de excepção."),
                    title=_("Data de vencimento inválida"),
                )
        if self.is_active:
            self._validate_no_overlap()

    def _validate_no_overlap(self):
        """Prevent two active exceptions from overlapping in time."""
        if not self.applies_from or not self.applies_until:
            return
        overlap = frappe.db.sql(
            """
            SELECT name FROM `tabPayment Exception`
            WHERE is_active = 1
              AND name != %s
              AND applies_from <= %s
              AND applies_until >= %s
            LIMIT 1
            """,
            (self.name or "", self.applies_until, self.applies_from),
        )
        if overlap:
            frappe.throw(
                _("Já existe uma Excepção de Pagamento activa que se sobrepõe a este período: "
                  "<b>{0}</b>. Desactive-a antes de criar uma nova.").format(overlap[0][0]),
                title=_("Sobreposição de excepções"),
            )


def get_active_exception(for_date=None):
    """Return the active Payment Exception covering for_date, or None."""
    check_date = for_date or getdate(today())
    rows = frappe.get_all(
        "Payment Exception",
        filters={
            "is_active": 1,
            "applies_from": ("<=", check_date),
            "applies_until": (">=", check_date),
        },
        fields=["name", "extended_due_date", "disable_penalties", "reason"],
        limit=1,
    )
    return rows[0] if rows else None
