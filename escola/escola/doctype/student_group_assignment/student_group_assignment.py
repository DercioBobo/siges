import frappe
from frappe import _
from frappe.model.document import Document


class StudentGroupAssignment(Document):
    def validate(self):
        self._validate_class_group_belongs()
        self._validate_duplicate_active_assignment()
        self._validate_class_group_capacity()

    def _validate_class_group_belongs(self):
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

    def _validate_duplicate_active_assignment(self):
        if self.status != "Activa":
            return
        existing = frappe.db.get_value(
            "Student Group Assignment",
            {
                "student": self.student,
                "academic_year": self.academic_year,
                "status": "Activa",
                "name": ("!=", self.name),
            },
            "name",
        )
        if existing:
            frappe.throw(
                _("O aluno já possui uma alocação activa para o Ano Lectivo "
                  "<b>{0}</b>: <b>{1}</b>. Encerre ou transfira a alocação "
                  "existente antes de criar uma nova.").format(
                    self.academic_year, existing
                ),
                title=_("Alocação duplicada"),
            )

    def _validate_class_group_capacity(self):
        if not self.class_group or self.status != "Activa":
            return
        max_students = frappe.db.get_value(
            "Class Group", self.class_group, "max_students"
        )
        if not max_students:
            return
        active_count = frappe.db.count(
            "Student Group Assignment",
            {
                "class_group": self.class_group,
                "academic_year": self.academic_year,
                "status": "Activa",
                "name": ("!=", self.name),
            },
        )
        if active_count >= max_students:
            frappe.throw(
                _("A Turma <b>{0}</b> atingiu a capacidade máxima de "
                  "<b>{1}</b> alunos.").format(self.class_group, max_students),
                title=_("Capacidade esgotada"),
            )
