import frappe
from frappe.model.document import Document


class Guardian(Document):
    def before_save(self):
        parts = filter(None, [self.first_name, self.last_name])
        self.full_name = " ".join(parts)

    def after_insert(self):
        try:
            from escola.escola.portal import provision_portal_user
            provision_portal_user(self, "Encarregado de Educação")
        except Exception:
            frappe.log_error(
                title="Escola — falha ao criar utilizador do portal (Encarregado)",
                message=frappe.get_traceback(),
            )
