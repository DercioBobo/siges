import frappe
from frappe import _
from frappe.model.document import Document


class ClassSubjectAssignment(Document):
    def validate(self):
        self._validate_no_duplicate_active_subject()
        self._validate_teacher_active()

    def _validate_no_duplicate_active_subject(self):
        if not self.is_active:
            return
        existing = frappe.db.get_value(
            "Class Subject Assignment",
            {
                "school_class": self.school_class,
                "academic_year": self.academic_year,
                "subject": self.subject,
                "is_active": 1,
                "name": ("!=", self.name),
            },
            "name",
        )
        if existing:
            frappe.throw(
                _("A disciplina <b>{0}</b> já está atribuída à Classe <b>{1}</b> "
                  "no Ano Lectivo <b>{2}</b>: <b>{3}</b>.").format(
                    self.subject, self.school_class, self.academic_year, existing
                ),
                title=_("Atribuição duplicada"),
            )

    def _validate_teacher_active(self):
        if not self.teacher:
            return
        is_active = frappe.db.get_value("Teacher", self.teacher, "is_active")
        if not is_active:
            frappe.throw(
                _("O professor <b>{0}</b> não está activo.").format(self.teacher),
                title=_("Professor inactivo"),
            )
