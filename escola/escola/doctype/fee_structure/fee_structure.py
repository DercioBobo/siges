import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate


class FeeStructure(Document):
    def validate(self):
        self._validate_has_lines()
        self._validate_dates()
        self._validate_line_amounts()
        self._validate_no_duplicate_lines()

    def _validate_has_lines(self):
        if not self.fee_lines:
            frappe.throw(_("O Plano de Propinas deve ter pelo menos um componente de cobrança."))

    def _validate_dates(self):
        if self.start_date and self.end_date and getdate(self.end_date) <= getdate(self.start_date):
            frappe.throw(_("A Data de Fim deve ser posterior à Data de Início."))

    def _validate_line_amounts(self):
        for line in self.fee_lines:
            if line.amount <= 0:
                frappe.throw(
                    _("O valor da linha '{0}' deve ser maior que zero.").format(
                        line.fee_category or line.item_code
                    )
                )

    def _validate_no_duplicate_lines(self):
        seen = set()
        for line in self.fee_lines:
            key = (line.fee_category, line.item_code)
            if key in seen:
                frappe.throw(
                    _("A combinação Categoria '{0}' + Item '{1}' está duplicada no Plano.").format(
                        line.fee_category, line.item_code
                    )
                )
            seen.add(key)
