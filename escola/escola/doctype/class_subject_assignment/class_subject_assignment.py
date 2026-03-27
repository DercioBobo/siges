import frappe
from frappe import _
from frappe.model.document import Document


class ClassSubjectAssignment(Document):
    def validate(self):
        self._validate_class_group_compatibility()
        self._validate_no_duplicate_active_subject()
        self._validate_teacher_active()

    def _validate_class_group_compatibility(self):
        if not self.class_group:
            return
        cg = frappe.db.get_value(
            "Class Group",
            self.class_group,
            ["academic_year", "school_class", "is_active"],
            as_dict=True,
        )
        if not cg:
            return
        if cg.academic_year != self.academic_year:
            frappe.throw(
                _("A Turma <b>{0}</b> pertence ao Ano Lectivo <b>{1}</b>, "
                  "não ao Ano Lectivo <b>{2}</b>.").format(
                    self.class_group, cg.academic_year, self.academic_year
                ),
                title=_("Turma incompatível"),
            )
        if self.school_class and cg.school_class != self.school_class:
            frappe.throw(
                _("A Turma <b>{0}</b> pertence à Classe <b>{1}</b>, "
                  "não à Classe <b>{2}</b>.").format(
                    self.class_group, cg.school_class, self.school_class
                ),
                title=_("Turma incompatível"),
            )
        if not cg.is_active:
            frappe.throw(
                _("A Turma <b>{0}</b> não está activa.").format(self.class_group),
                title=_("Turma inactiva"),
            )

    def _validate_no_duplicate_active_subject(self):
        if not self.is_active:
            return
        existing = frappe.db.get_value(
            "Class Subject Assignment",
            {
                "class_group": self.class_group,
                "subject": self.subject,
                "is_active": 1,
                "name": ("!=", self.name),
            },
            "name",
        )
        if existing:
            frappe.throw(
                _("A disciplina <b>{0}</b> já está atribuída à Turma <b>{1}</b> "
                  "de forma activa: <b>{2}</b>. Desactive a atribuição anterior "
                  "antes de criar uma nova.").format(
                    self.subject, self.class_group, existing
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
