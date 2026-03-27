import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate


class AcademicTerm(Document):
    def validate(self):
        self._validate_dates()
        self._validate_dates_within_academic_year()

    def _validate_dates(self):
        if self.start_date and self.end_date:
            if getdate(self.end_date) <= getdate(self.start_date):
                frappe.throw(
                    _("A Data de Fim deve ser posterior à Data de Início."),
                    title=_("Datas inválidas"),
                )

    def _validate_dates_within_academic_year(self):
        if not (self.academic_year and self.start_date and self.end_date):
            return
        ay = frappe.db.get_value(
            "Academic Year",
            self.academic_year,
            ["start_date", "end_date"],
            as_dict=True,
        )
        if not ay or not ay.start_date or not ay.end_date:
            return
        if getdate(self.start_date) < getdate(ay.start_date) or getdate(self.end_date) > getdate(ay.end_date):
            frappe.msgprint(
                _("Atenção: as datas do Período Académico <b>{0}</b> estão fora "
                  "do intervalo do Ano Lectivo <b>{1}</b> ({2} a {3}).").format(
                    self.term_name,
                    self.academic_year,
                    frappe.format(ay.start_date, {"fieldtype": "Date"}),
                    frappe.format(ay.end_date, {"fieldtype": "Date"}),
                ),
                title=_("Datas fora do intervalo"),
                indicator="orange",
            )
