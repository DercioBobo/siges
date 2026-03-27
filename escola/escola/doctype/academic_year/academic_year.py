import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate


class AcademicYear(Document):
    def validate(self):
        self._validate_dates()
        if self.is_active:
            self._ensure_single_active()

    def _validate_dates(self):
        if self.start_date and self.end_date:
            if getdate(self.end_date) <= getdate(self.start_date):
                frappe.throw(
                    _("A Data de Fim deve ser posterior à Data de Início."),
                    title=_("Datas inválidas"),
                )

    def _ensure_single_active(self):
        existing = frappe.db.get_value(
            "Academic Year",
            {"is_active": 1, "name": ("!=", self.name)},
            "year_name",
        )
        if existing:
            frappe.throw(
                _("O ano lectivo <b>{0}</b> já está marcado como Ano Actual. "
                  "Desactive-o primeiro antes de activar este.").format(existing),
                title=_("Ano Actual duplicado"),
            )
