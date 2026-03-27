import frappe
from frappe import _
from frappe.model.document import Document


class Student(Document):
    def before_insert(self):
        self._generate_student_code()

    def before_save(self):
        self._sync_full_name()
        if not self.current_status:
            self.current_status = "Activo"

    def _sync_full_name(self):
        parts = filter(None, [self.first_name, self.last_name])
        self.full_name = " ".join(parts)

    def _generate_student_code(self):
        if self.student_code:
            return
        last = frappe.db.sql(
            "SELECT student_code FROM `tabStudent` "
            "WHERE student_code LIKE 'ALU-%' "
            "ORDER BY student_code DESC LIMIT 1"
        )
        if last and last[0][0]:
            try:
                seq = int(last[0][0].split("-")[1]) + 1
            except (IndexError, ValueError):
                seq = 1
        else:
            seq = 1
        self.student_code = "ALU-{:05d}".format(seq)
