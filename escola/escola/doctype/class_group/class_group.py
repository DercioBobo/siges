import frappe
from frappe import _
from frappe.model.document import Document


class ClassGroup(Document):
    def validate(self):
        self._validate_class_teacher()
        if self.max_students is not None and self.max_students < 1:
            frappe.throw(
                _("A Capacidade Máxima deve ser um número positivo."),
                title=_("Capacidade inválida"),
            )

    def _validate_class_teacher(self):
        if not self.class_teacher:
            return
        is_active = frappe.db.get_value("Teacher", self.class_teacher, "is_active")
        if not is_active:
            frappe.throw(
                _("O professor <b>{0}</b> não está activo e não pode ser designado "
                  "como Professor Titular.").format(self.class_teacher),
                title=_("Professor inactivo"),
            )
