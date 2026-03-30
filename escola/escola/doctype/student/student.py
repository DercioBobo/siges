import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, today


def _calc_age(date_of_birth):
    if not date_of_birth:
        return None
    dob = getdate(date_of_birth)
    tod = getdate(today())
    age = tod.year - dob.year - ((tod.month, tod.day) < (dob.month, dob.day))
    return age if age >= 0 else None


def update_all_student_ages():
    """Daily scheduler job — recalculates idade for every student with a date_of_birth."""
    rows = frappe.db.get_all(
        "Student",
        filters=[["date_of_birth", "is", "set"]],
        fields=["name", "date_of_birth"],
    )
    for row in rows:
        age = _calc_age(row.date_of_birth)
        if age is not None:
            frappe.db.set_value("Student", row.name, "idade", age, update_modified=False)
    if rows:
        frappe.db.commit()


class Student(Document):
    def before_insert(self):
        self._generate_student_code()

    def before_save(self):
        self._sync_full_name()
        self.idade = _calc_age(self.date_of_birth)
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
