import re

import frappe
from frappe import _
from frappe.model.document import Document

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class Teacher(Document):
    def before_save(self):
        self._sync_full_name()

    def validate(self):
        self._validate_email()

    def _sync_full_name(self):
        parts = filter(None, [self.first_name, self.last_name])
        self.full_name = " ".join(parts)

    def _validate_email(self):
        if self.email and not EMAIL_PATTERN.match(self.email):
            frappe.throw(
                _("O endereço de email <b>{0}</b> não é válido.").format(self.email),
                title=_("Email inválido"),
            )
