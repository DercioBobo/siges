import frappe
from frappe import _
from frappe.model.document import Document


class Inscricao(Document):
    def validate(self):
        self._validate_no_duplicate()
        self._validate_class_group()
        self._validate_student_active()

    def on_submit(self):
        self._create_sga()

    def on_cancel(self):
        self._close_sga()

    # ------------------------------------------------------------------

    def _validate_no_duplicate(self):
        existing = frappe.db.get_value(
            "Inscricao",
            {
                "student": self.student,
                "academic_year": self.academic_year,
                "docstatus": 1,
                "name": ("!=", self.name),
            },
            "name",
        )
        if existing:
            frappe.throw(
                _("O aluno <b>{0}</b> já tem uma Inscrição activa para o Ano Lectivo "
                  "<b>{1}</b>: <b>{2}</b>.").format(
                    self.student, self.academic_year, existing
                ),
                title=_("Inscrição duplicada"),
            )

    def _validate_class_group(self):
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
                title=_("Classe incompatível"),
            )
        if not cg.is_active:
            frappe.throw(
                _("A Turma <b>{0}</b> não está activa.").format(self.class_group),
                title=_("Turma inactiva"),
            )

    def _validate_student_active(self):
        is_active = frappe.db.get_value("Student", self.student, "is_active")
        if not is_active:
            frappe.throw(
                _("O aluno <b>{0}</b> não está activo.").format(self.student),
                title=_("Aluno inactivo"),
            )

    def _create_sga(self):
        frappe.get_doc({
            "doctype": "Student Group Assignment",
            "student": self.student,
            "class_group": self.class_group,
            "academic_year": self.academic_year,
            "school_class": self.school_class,
            "assignment_date": self.enrollment_date,
            "status": "Activa",
            "notes": _("Criado automaticamente pela Inscrição {0}.").format(self.name),
        }).insert(ignore_permissions=True)

    def _close_sga(self):
        sga_name = frappe.db.get_value(
            "Student Group Assignment",
            {
                "student": self.student,
                "class_group": self.class_group,
                "status": "Activa",
            },
            "name",
        )
        if sga_name:
            sga = frappe.get_doc("Student Group Assignment", sga_name)
            sga.status = "Encerrada"
            sga.save(ignore_permissions=True)


@frappe.whitelist()
def get_available_turmas(academic_year, school_class):
    """Return all active Class Groups for the given year+class with student counts."""
    return frappe.get_all(
        "Class Group",
        filters={"academic_year": academic_year, "school_class": school_class, "is_active": 1},
        fields=["name", "group_name", "student_count", "max_students", "shift"],
        order_by="group_name asc",
    )
