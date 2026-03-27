import frappe
from frappe import _
from frappe.model.document import Document


class AssessmentScheme(Document):
    def validate(self):
        self._validate_has_components()
        self._validate_weights()

    def _validate_has_components(self):
        if not self.components:
            frappe.throw(
                _("O Modelo de Avaliação deve ter pelo menos um componente."),
                title=_("Componentes obrigatórios"),
            )

    def _validate_weights(self):
        for row in self.components:
            if row.weight is None or row.weight <= 0:
                frappe.throw(
                    _("O peso do componente <b>{0}</b> (linha {1}) deve ser "
                      "maior que zero.").format(
                        row.evaluation_type or "–", row.idx
                    ),
                    title=_("Peso inválido"),
                )
        total = sum(row.weight or 0 for row in self.components)
        if abs(total - 100) > 0.01:
            frappe.throw(
                _("A soma dos pesos dos componentes deve ser exactamente "
                  "<b>100%</b>. Soma actual: <b>{0}%</b>.").format(
                    round(total, 2)
                ),
                title=_("Soma de pesos inválida"),
            )
