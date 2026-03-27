import frappe
from frappe.model.document import Document


class Guardian(Document):
    def before_save(self):
        parts = filter(None, [self.first_name, self.last_name])
        self.full_name = " ".join(parts)
