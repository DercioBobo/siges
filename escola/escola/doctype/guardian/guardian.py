import json
import frappe
from frappe.model.document import Document


class Guardian(Document):
    def before_insert(self):
        self._sync_full_name()

    def before_save(self):
        self._sync_full_name()

    def _sync_full_name(self):
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


# ---------------------------------------------------------------------------
# Whitelisted helpers for the Guardian form
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_students(guardian):
    """Return all students whose primary_guardian is this guardian."""
    return frappe.get_all(
        "Student",
        filters={"primary_guardian": guardian},
        fields=["name", "full_name", "student_code",
                "current_class_group", "current_status", "financial_status"],
        order_by="full_name asc",
    )


@frappe.whitelist()
def search_students(query, exclude_guardian):
    """Search active students not yet linked to this guardian."""
    conditions = ["`tabStudent`.`current_status` != 'Desistente'"]
    params = {}

    if query:
        conditions.append(
            "(`tabStudent`.`full_name` LIKE %(q)s OR `tabStudent`.`student_code` LIKE %(q)s)"
        )
        params["q"] = f"%{query}%"

    where = " AND ".join(conditions)

    rows = frappe.db.sql(f"""
        SELECT name, full_name, student_code, current_class_group,
               current_status, primary_guardian
        FROM `tabStudent`
        WHERE {where}
          AND (primary_guardian IS NULL OR primary_guardian != %(guardian)s)
        ORDER BY full_name ASC
        LIMIT 60
    """, {**params, "guardian": exclude_guardian}, as_dict=True)

    return rows


@frappe.whitelist()
def assign_students(guardian, students):
    """Set primary_guardian on each student in the list."""
    if isinstance(students, str):
        students = json.loads(students)
    for student in students:
        frappe.db.set_value("Student", student, "primary_guardian", guardian)


@frappe.whitelist()
def remove_student(guardian, student):
    """Clear primary_guardian on a student (only if it matches this guardian)."""
    current = frappe.db.get_value("Student", student, "primary_guardian")
    if current == guardian:
        frappe.db.set_value("Student", student, "primary_guardian", None)
