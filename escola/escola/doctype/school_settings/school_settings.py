import frappe
from frappe import _
from frappe.model.document import Document


class SchoolSettings(Document):
    def validate(self):
        self._validate_academic_term_belongs_to_year()
        self._validate_grading_thresholds()
        self._validate_income_account_company()

    def _validate_academic_term_belongs_to_year(self):
        if not (self.current_academic_year and self.current_academic_term):
            return
        term_year = frappe.db.get_value(
            "Academic Term", self.current_academic_term, "academic_year"
        )
        if term_year != self.current_academic_year:
            frappe.throw(
                _("O Período Académico <b>{0}</b> pertence ao Ano Lectivo <b>{1}</b>, "
                  "não ao Ano Lectivo <b>{2}</b> seleccionado.").format(
                    self.current_academic_term, term_year, self.current_academic_year
                ),
                title=_("Período incompatível"),
            )

    def _validate_grading_thresholds(self):
        max_grade = self.grading_scale_max or 20
        min_pass = self.minimum_passing_grade or 10
        recurso = self.recurso_threshold

        if min_pass > max_grade:
            frappe.throw(
                _("A Nota Mínima de Aprovação (<b>{0}</b>) não pode ser superior "
                  "à Nota Máxima da escala (<b>{1}</b>).").format(min_pass, max_grade),
                title=_("Configuração de avaliação inválida"),
            )
        if recurso is not None and recurso >= min_pass:
            frappe.throw(
                _("O Limiar de Recurso (<b>{0}</b>) deve ser inferior à Nota Mínima "
                  "de Aprovação (<b>{1}</b>).").format(recurso, min_pass),
                title=_("Limiar de recurso inválido"),
            )

    def _validate_income_account_company(self):
        """Ensure the income account belongs to the selected company."""
        if not (self.default_income_account and self.default_company):
            return
        account_company = frappe.db.get_value(
            "Account", self.default_income_account, "company"
        )
        if account_company and account_company != self.default_company:
            frappe.throw(
                _("A Conta de Receitas <b>{0}</b> pertence à empresa <b>{1}</b>, "
                  "não à empresa <b>{2}</b>.").format(
                    self.default_income_account, account_company, self.default_company
                ),
                title=_("Conta incompatível"),
            )
