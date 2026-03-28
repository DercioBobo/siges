import frappe
from frappe.model.document import Document


class SchoolClass(Document):
    def validate(self):
        if self.class_level is not None and self.class_level < 1:
            frappe.throw(
                frappe._("O Nível da Classe deve ser um número positivo."),
                title=frappe._("Nível inválido"),
            )
        if self.minimum_passing_grade is not None and self.minimum_passing_grade < 0:
            frappe.throw(
                frappe._("A Nota Mínima de Aprovação não pode ser negativa."),
                title=frappe._("Nota inválida"),
            )
        if self.default_teacher:
            is_active = frappe.db.get_value("Teacher", self.default_teacher, "is_active")
            if not is_active:
                frappe.throw(
                    frappe._("O professor <b>{0}</b> não está activo.").format(
                        self.default_teacher
                    ),
                    title=frappe._("Professor inactivo"),
                )
