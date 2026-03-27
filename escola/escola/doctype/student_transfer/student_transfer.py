import frappe
from frappe import _
from frappe.model.document import Document


class StudentTransfer(Document):
    # ------------------------------------------------------------------
    # Lifecycle hooks
    # ------------------------------------------------------------------

    def validate(self):
        self._validate_active_enrollment()
        self._validate_origin_fields()
        self._validate_destination()
        self._validate_not_duplicate_transfer()

    def on_submit(self):
        self._execute_transfer()
        self.db_set("status", "Concluída")

    def on_cancel(self):
        self._revert_transfer()
        self.db_set("status", "Cancelada")

    # ------------------------------------------------------------------
    # Validation methods
    # ------------------------------------------------------------------

    def _validate_active_enrollment(self):
        if not (self.student and self.academic_year and self.from_enrollment):
            return
        enr = frappe.db.get_value(
            "Student Enrollment",
            self.from_enrollment,
            ["student", "academic_year", "enrollment_status", "school_class"],
            as_dict=True,
        )
        if not enr:
            frappe.throw(
                _("A Inscrição <b>{0}</b> não foi encontrada.").format(
                    self.from_enrollment
                ),
                title=_("Inscrição inválida"),
            )
        if enr.student != self.student:
            frappe.throw(
                _("A Inscrição <b>{0}</b> não pertence ao aluno "
                  "seleccionado.").format(self.from_enrollment),
                title=_("Inscrição incompatível"),
            )
        if enr.academic_year != self.academic_year:
            frappe.throw(
                _("A Inscrição <b>{0}</b> pertence ao Ano Lectivo <b>{1}</b>, "
                  "não ao Ano Lectivo <b>{2}</b>.").format(
                    self.from_enrollment, enr.academic_year, self.academic_year
                ),
                title=_("Ano Lectivo incompatível"),
            )
        if enr.enrollment_status != "Activa":
            frappe.throw(
                _("A Inscrição <b>{0}</b> não está activa (estado: "
                  "<b>{1}</b>). Apenas alunos com inscrição activa podem "
                  "ser transferidos.").format(
                    self.from_enrollment, enr.enrollment_status
                ),
                title=_("Inscrição inactiva"),
            )
        # Sync from_school_class from enrollment if not yet set
        if not self.from_school_class and enr.school_class:
            self.from_school_class = enr.school_class

    def _validate_origin_fields(self):
        if not self.from_class_group:
            return
        # Confirm the student actually has an active assignment in that turma
        active_assignment = frappe.db.get_value(
            "Student Group Assignment",
            {
                "student": self.student,
                "academic_year": self.academic_year,
                "class_group": self.from_class_group,
                "status": "Activa",
            },
            "name",
        )
        if not active_assignment:
            frappe.throw(
                _("O aluno não tem uma alocação activa na Turma de Origem "
                  "<b>{0}</b> para o Ano Lectivo <b>{1}</b>.").format(
                    self.from_class_group, self.academic_year
                ),
                title=_("Alocação de origem não encontrada"),
            )
        # Store for use in on_submit / on_cancel
        self.from_assignment = active_assignment

    def _validate_destination(self):
        if not self.to_class_group:
            return
        # Destination must differ from origin
        if self.to_class_group == self.from_class_group:
            frappe.throw(
                _("A Turma de Destino não pode ser igual à Turma de Origem."),
                title=_("Destino inválido"),
            )
        # Destination turma must belong to same academic year
        cg = frappe.db.get_value(
            "Class Group",
            self.to_class_group,
            ["academic_year", "is_active", "max_students"],
            as_dict=True,
        )
        if not cg:
            return
        if cg.academic_year != self.academic_year:
            frappe.throw(
                _("A Turma de Destino <b>{0}</b> pertence ao Ano Lectivo "
                  "<b>{1}</b>, não ao Ano Lectivo <b>{2}</b>.").format(
                    self.to_class_group, cg.academic_year, self.academic_year
                ),
                title=_("Turma de destino incompatível"),
            )
        if not cg.is_active:
            frappe.throw(
                _("A Turma de Destino <b>{0}</b> não está activa.").format(
                    self.to_class_group
                ),
                title=_("Turma de destino inactiva"),
            )
        # Capacity check
        if cg.max_students:
            active_count = frappe.db.count(
                "Student Group Assignment",
                {
                    "class_group": self.to_class_group,
                    "academic_year": self.academic_year,
                    "status": "Activa",
                },
            )
            if active_count >= cg.max_students:
                frappe.throw(
                    _("A Turma de Destino <b>{0}</b> já atingiu a capacidade "
                      "máxima de <b>{1}</b> alunos.").format(
                        self.to_class_group, cg.max_students
                    ),
                    title=_("Capacidade esgotada"),
                )

    def _validate_not_duplicate_transfer(self):
        existing = frappe.db.get_value(
            "Student Transfer",
            {
                "student": self.student,
                "academic_year": self.academic_year,
                "from_class_group": self.from_class_group,
                "to_class_group": self.to_class_group,
                "transfer_date": self.transfer_date,
                "status": "Concluída",
                "name": ("!=", self.name),
            },
            "name",
        )
        if existing:
            frappe.throw(
                _("Já existe uma transferência concluída com os mesmos dados "
                  "para este aluno nesta data: <b>{0}</b>.").format(existing),
                title=_("Transferência duplicada"),
            )

    # ------------------------------------------------------------------
    # Submit / Cancel actions
    # ------------------------------------------------------------------

    def _execute_transfer(self):
        """Close the active origin assignment and open a new one in the destination."""
        # Find the current active assignment (re-query at submit time)
        old_assignment_name = frappe.db.get_value(
            "Student Group Assignment",
            {
                "student": self.student,
                "academic_year": self.academic_year,
                "class_group": self.from_class_group,
                "status": "Activa",
            },
            "name",
        )
        if not old_assignment_name:
            frappe.throw(
                _("Não foi encontrada uma alocação activa na Turma de Origem "
                  "<b>{0}</b>. A transferência não pode ser concluída.").format(
                    self.from_class_group
                ),
                title=_("Alocação não encontrada"),
            )

        # Close old assignment
        frappe.db.set_value(
            "Student Group Assignment",
            old_assignment_name,
            "status",
            "Transferida",
        )
        self.db_set("from_assignment", old_assignment_name)

        # Create new assignment in destination turma
        new_doc = frappe.new_doc("Student Group Assignment")
        new_doc.student = self.student
        new_doc.academic_year = self.academic_year
        new_doc.school_class = self.to_school_class
        new_doc.class_group = self.to_class_group
        new_doc.enrollment = self.from_enrollment
        new_doc.assignment_date = self.transfer_date
        new_doc.status = "Activa"
        new_doc.notes = _(
            "Criado automaticamente pela Transferência {0}."
        ).format(self.name)
        new_doc.flags.ignore_permissions = True
        new_doc.insert()

        self.db_set("new_assignment", new_doc.name)
        frappe.msgprint(
            _("Transferência concluída. Nova alocação criada: "
              "<b>{0}</b>.").format(new_doc.name),
            title=_("Transferência concluída"),
            indicator="green",
        )

    def _revert_transfer(self):
        """Undo the transfer: close the new assignment, reactivate the original."""
        if self.new_assignment:
            assignment_exists = frappe.db.exists(
                "Student Group Assignment", self.new_assignment
            )
            if assignment_exists:
                frappe.db.set_value(
                    "Student Group Assignment",
                    self.new_assignment,
                    "status",
                    "Encerrada",
                )

        if self.from_assignment:
            assignment_exists = frappe.db.exists(
                "Student Group Assignment", self.from_assignment
            )
            if assignment_exists:
                frappe.db.set_value(
                    "Student Group Assignment",
                    self.from_assignment,
                    "status",
                    "Activa",
                )
        frappe.msgprint(
            _("Transferência cancelada. A alocação original foi reactivada."),
            title=_("Transferência cancelada"),
            indicator="orange",
        )
