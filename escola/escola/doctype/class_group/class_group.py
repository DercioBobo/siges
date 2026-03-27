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


@frappe.whitelist()
def rebuild_roster(class_group_name):
    """
    Rebuild the student roster from active Student Group Assignments.
    Safe to call at any time — idempotent.
    """
    frappe.db.delete("Class Group Student", {"parent": class_group_name})

    assignments = frappe.get_all(
        "Student Group Assignment",
        filters={"class_group": class_group_name, "status": "Activa"},
        fields=["name", "student"],
        order_by="student asc",
    )

    for idx, sga in enumerate(assignments, start=1):
        frappe.get_doc({
            "doctype": "Class Group Student",
            "parent": class_group_name,
            "parentfield": "students",
            "parenttype": "Class Group",
            "idx": idx,
            "student": sga.student,
            "assignment": sga.name,
        }).insert(ignore_permissions=True)

    count = len(assignments)
    frappe.db.set_value(
        "Class Group", class_group_name, "student_count", count, update_modified=False
    )
    frappe.db.commit()
    return count


def sync_student_in_rosters(doc, method=None):
    """
    Called via doc_events when a Student record is saved.
    Updates student_name in every Class Group Student row for this student.
    """
    if not doc.student_name:
        return
    frappe.db.sql(
        """UPDATE `tabClass Group Student`
           SET student_name = %s
           WHERE student = %s""",
        (doc.student_name, doc.name),
    )
