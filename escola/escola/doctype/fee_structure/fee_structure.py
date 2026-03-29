import frappe
from frappe import _
from frappe.model.document import Document


class FeeStructure(Document):
    def validate(self):
        self._validate_has_lines()
        self._validate_line_amounts()
        self._validate_line_billing_mode()
        self._validate_no_duplicate_lines()
        self._validate_uniqueness()

    def _validate_has_lines(self):
        if not self.fee_lines:
            frappe.throw(_("O Plano de Propinas deve ter pelo menos um componente de cobrança."))

    def _validate_line_amounts(self):
        for line in self.fee_lines:
            if line.amount <= 0:
                frappe.throw(
                    _("O valor da linha '{0}' deve ser maior que zero.").format(
                        line.fee_category or line.item_code
                    )
                )

    def _validate_line_billing_mode(self):
        for line in self.fee_lines:
            if not line.billing_mode:
                frappe.throw(
                    _("A linha '{0}' não tem Modo de Cobrança definido.").format(
                        line.fee_category or line.item_code
                    )
                )

    def _validate_no_duplicate_lines(self):
        seen = set()
        for line in self.fee_lines:
            key = (line.fee_category, line.item_code, line.billing_mode)
            if key in seen:
                frappe.throw(
                    _("A combinação Categoria '{0}' + Item '{1}' + Modo '{2}' está duplicada no Plano.").format(
                        line.fee_category, line.item_code, line.billing_mode
                    )
                )
            seen.add(key)

    def _validate_uniqueness(self):
        """Only one active Fee Structure per school_class (+ academic_year if set)."""
        if not self.is_active or not self.school_class:
            return

        filters = {
            "school_class": self.school_class,
            "is_active": 1,
            "name": ("!=", self.name),
        }
        if self.academic_year:
            filters["academic_year"] = self.academic_year

        existing = frappe.db.get_value("Fee Structure", filters, "name")
        if existing:
            year_label = f" / {self.academic_year}" if self.academic_year else ""
            frappe.throw(
                _("Já existe um Plano de Propinas activo para a Classe <b>{0}{1}</b>: <b>{2}</b>. "
                  "Desactive o plano anterior antes de criar um novo.").format(
                    self.school_class, year_label, existing
                ),
                title=_("Plano duplicado"),
            )
