import re

import frappe
from frappe import _
from frappe.model.document import Document

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class Teacher(Document):
    def before_insert(self):
        self._sync_full_name()
        self._generate_teacher_code()

    def before_save(self):
        self._sync_full_name()

    def validate(self):
        self._validate_email()

    def _sync_full_name(self):
        parts = filter(None, [self.first_name, self.last_name])
        self.full_name = " ".join(parts)

    def _generate_teacher_code(self):
        if self.teacher_code:
            return
        last = frappe.db.sql(
            "SELECT teacher_code FROM `tabTeacher` "
            "WHERE teacher_code LIKE 'PROF-%' "
            "ORDER BY teacher_code DESC LIMIT 1"
        )
        if last and last[0][0]:
            try:
                seq = int(last[0][0].split("-")[1]) + 1
            except (IndexError, ValueError):
                seq = 1
        else:
            seq = 1
        self.teacher_code = "PROF-{:05d}".format(seq)

    def after_insert(self):
        try:
            from escola.escola.portal import provision_portal_user
            provision_portal_user(self, "Professor")
        except Exception:
            frappe.log_error(
                title="Escola — falha ao criar utilizador do portal (Professor)",
                message=frappe.get_traceback(),
            )

    def _validate_email(self):
        if self.email and not EMAIL_PATTERN.match(self.email):
            frappe.throw(
                _("O endereço de email <b>{0}</b> não é válido.").format(self.email),
                title=_("Email inválido"),
            )
