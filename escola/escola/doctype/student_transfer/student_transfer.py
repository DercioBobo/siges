import frappe
from frappe import _
from frappe.model.document import Document

_INTERNAL = "Interna (Entre Turmas)"
_EXIT = "Saída (Para Outra Escola)"
_ENTRY = "Entrada (Outra Escola)"


def _safe_set_student_status(student, status):
    """Set Student.current_status if the field exists (ERPNext version-dependent)."""
    try:
        frappe.db.set_value("Student", student, "current_status", status, update_modified=False)
    except Exception:
        pass


class StudentTransfer(Document):
    # ------------------------------------------------------------------
    # Lifecycle hooks
    # ------------------------------------------------------------------

    def validate(self):
        transfer_type = self.transfer_type or _INTERNAL

        if transfer_type == _INTERNAL:
            self._validate_active_enrollment()
            self._validate_origin_fields()
            self._validate_destination()
        elif transfer_type == _EXIT:
            self._validate_exit_transfer()
        elif transfer_type == _ENTRY:
            self._validate_entry_transfer()

        self._validate_not_duplicate_transfer()

    def on_submit(self):
        transfer_type = self.transfer_type or _INTERNAL

        if transfer_type == _INTERNAL:
            self._handle_internal_transfer()
        elif transfer_type == _EXIT:
            self._handle_exit_transfer()
        elif transfer_type == _ENTRY:
            self._handle_entry_transfer()

        self.db_set("status", "Concluída")

    def on_cancel(self):
        transfer_type = self.transfer_type or _INTERNAL

        if transfer_type == _INTERNAL:
            self._revert_internal_transfer()
        elif transfer_type == _EXIT:
            self._revert_exit_transfer()
        elif transfer_type == _ENTRY:
            self._revert_entry_transfer()

        self.db_set("status", "Cancelada")

    # ------------------------------------------------------------------
    # Validation — Internal
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
                _("A Inscrição <b>{0}</b> não foi encontrada.").format(self.from_enrollment),
                title=_("Inscrição inválida"),
            )
        if enr.student != self.student:
            frappe.throw(
                _("A Inscrição <b>{0}</b> não pertence ao aluno seleccionado.").format(
                    self.from_enrollment
                ),
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
                _("A Inscrição <b>{0}</b> não está activa (estado: <b>{1}</b>). "
                  "Apenas alunos com inscrição activa podem ser transferidos.").format(
                    self.from_enrollment, enr.enrollment_status
                ),
                title=_("Inscrição inactiva"),
            )
        if not self.from_school_class and enr.school_class:
            self.from_school_class = enr.school_class

    def _validate_origin_fields(self):
        if not self.from_class_group:
            return
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
        self.from_assignment = active_assignment

    def _validate_destination(self):
        if not self.to_class_group:
            return
        if self.to_class_group == self.from_class_group:
            frappe.throw(
                _("A Turma de Destino não pode ser igual à Turma de Origem."),
                title=_("Destino inválido"),
            )
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
                _("A Turma de Destino <b>{0}</b> pertence ao Ano Lectivo <b>{1}</b>, "
                  "não ao Ano Lectivo <b>{2}</b>.").format(
                    self.to_class_group, cg.academic_year, self.academic_year
                ),
                title=_("Turma de destino incompatível"),
            )
        if not cg.is_active:
            frappe.throw(
                _("A Turma de Destino <b>{0}</b> não está activa.").format(self.to_class_group),
                title=_("Turma de destino inactiva"),
            )
        if cg.max_students:
            active_count = frappe.db.count(
                "Student Group Assignment",
                {"class_group": self.to_class_group, "academic_year": self.academic_year, "status": "Activa"},
            )
            if active_count >= cg.max_students:
                frappe.throw(
                    _("A Turma de Destino <b>{0}</b> já atingiu a capacidade máxima "
                      "de <b>{1}</b> alunos.").format(self.to_class_group, cg.max_students),
                    title=_("Capacidade esgotada"),
                )

    # ------------------------------------------------------------------
    # Validation — Exit
    # ------------------------------------------------------------------

    def _validate_exit_transfer(self):
        if not (self.student and self.academic_year):
            return
        has_assignment = frappe.db.exists(
            "Student Group Assignment",
            {"student": self.student, "academic_year": self.academic_year, "status": "Activa"},
        )
        if not has_assignment:
            frappe.throw(
                _("O aluno <b>{0}</b> não tem alocações activas no Ano Lectivo <b>{1}</b>. "
                  "Não é possível registar uma saída.").format(self.student, self.academic_year),
                title=_("Sem alocação activa"),
            )

    # ------------------------------------------------------------------
    # Validation — Entry
    # ------------------------------------------------------------------

    def _validate_entry_transfer(self):
        if not self.entry_class_group:
            frappe.throw(
                _("Defina a <b>Turma de Destino</b> para a transferência de entrada."),
                title=_("Turma em falta"),
            )
        cg = frappe.db.get_value(
            "Class Group",
            self.entry_class_group,
            ["academic_year", "is_active", "max_students"],
            as_dict=True,
        )
        if not cg:
            return
        if cg.academic_year != self.academic_year:
            frappe.throw(
                _("A Turma de Destino <b>{0}</b> pertence ao Ano Lectivo <b>{1}</b>, "
                  "não ao Ano Lectivo <b>{2}</b>.").format(
                    self.entry_class_group, cg.academic_year, self.academic_year
                ),
                title=_("Turma incompatível"),
            )
        if not cg.is_active:
            frappe.throw(
                _("A Turma de Destino <b>{0}</b> não está activa.").format(self.entry_class_group),
                title=_("Turma inactiva"),
            )
        if cg.max_students:
            active_count = frappe.db.count(
                "Student Group Assignment",
                {"class_group": self.entry_class_group, "academic_year": self.academic_year, "status": "Activa"},
            )
            if active_count >= cg.max_students:
                frappe.throw(
                    _("A Turma de Destino <b>{0}</b> já atingiu a capacidade máxima "
                      "de <b>{1}</b> alunos.").format(self.entry_class_group, cg.max_students),
                    title=_("Capacidade esgotada"),
                )
        # Student must not already have an active enrollment this year
        if frappe.db.exists(
            "Student Enrollment",
            {"student": self.student, "academic_year": self.academic_year, "enrollment_status": "Activa"},
        ):
            frappe.throw(
                _("O aluno <b>{0}</b> já tem uma inscrição activa no Ano Lectivo <b>{1}</b>. "
                  "Utilize uma Transferência Interna em vez de Entrada.").format(
                    self.student, self.academic_year
                ),
                title=_("Inscrição já existente"),
            )

    # ------------------------------------------------------------------
    # Duplicate check (type-aware)
    # ------------------------------------------------------------------

    def _validate_not_duplicate_transfer(self):
        filters = {
            "student": self.student,
            "academic_year": self.academic_year,
            "transfer_type": self.transfer_type or _INTERNAL,
            "status": "Concluída",
            "name": ("!=", self.name),
        }
        if (self.transfer_type or _INTERNAL) == _INTERNAL:
            if self.from_class_group:
                filters["from_class_group"] = self.from_class_group
            if self.to_class_group:
                filters["to_class_group"] = self.to_class_group

        existing = frappe.db.get_value("Student Transfer", filters, "name")
        if existing:
            frappe.throw(
                _("Já existe uma transferência do tipo <b>{0}</b> concluída para "
                  "este aluno neste ano lectivo: <b>{1}</b>.").format(
                    self.transfer_type, existing
                ),
                title=_("Transferência duplicada"),
            )

    # ------------------------------------------------------------------
    # Submit actions
    # ------------------------------------------------------------------

    def _handle_internal_transfer(self):
        """Close origin assignment and create a new one in the destination turma."""
        old_name = frappe.db.get_value(
            "Student Group Assignment",
            {
                "student": self.student,
                "academic_year": self.academic_year,
                "class_group": self.from_class_group,
                "status": "Activa",
            },
            "name",
        )
        if not old_name:
            frappe.throw(
                _("Não foi encontrada uma alocação activa na Turma de Origem <b>{0}</b>. "
                  "A transferência não pode ser concluída.").format(self.from_class_group),
                title=_("Alocação não encontrada"),
            )

        frappe.db.set_value("Student Group Assignment", old_name, "status", "Transferida")
        self.db_set("from_assignment", old_name)

        new_doc = frappe.new_doc("Student Group Assignment")
        new_doc.student = self.student
        new_doc.academic_year = self.academic_year
        new_doc.school_class = self.to_school_class
        new_doc.class_group = self.to_class_group
        new_doc.enrollment = self.from_enrollment
        new_doc.assignment_date = self.transfer_date
        new_doc.status = "Activa"
        new_doc.notes = _("Criado automaticamente pela Transferência {0}.").format(self.name)
        new_doc.flags.ignore_permissions = True
        new_doc.insert()

        self.db_set("new_assignment", new_doc.name)
        frappe.msgprint(
            _("Transferência concluída. Nova alocação criada: <b>{0}</b>.").format(new_doc.name),
            title=_("Transferência concluída"),
            indicator="green",
        )

    def _handle_exit_transfer(self):
        """Close all active assignments for the student and flag them as transferred out."""
        assignments = frappe.get_all(
            "Student Group Assignment",
            filters={"student": self.student, "academic_year": self.academic_year, "status": "Activa"},
            fields=["name"],
        )
        if not assignments:
            frappe.throw(
                _("Não foram encontradas alocações activas para o aluno no ano lectivo."),
                title=_("Alocações não encontradas"),
            )

        closed = []
        for a in assignments:
            frappe.db.set_value("Student Group Assignment", a.name, "status", "Transferida")
            closed.append(a.name)

        # Store first assignment for potential revert
        self.db_set("from_assignment", closed[0])

        # Mark enrollment as concluded
        active_enr = frappe.db.get_value(
            "Student Enrollment",
            {"student": self.student, "academic_year": self.academic_year, "enrollment_status": "Activa"},
            "name",
        )
        if active_enr:
            frappe.db.set_value("Student Enrollment", active_enr, "enrollment_status", "Cancelada")
            self.db_set("new_enrollment", active_enr)  # Reuse to track the updated enrollment

        _safe_set_student_status(self.student, "Transferido")

        frappe.msgprint(
            _("{0} alocação(ões) encerrada(s). Aluno registado como transferido.").format(len(closed)),
            title=_("Saída registada"),
            indicator="orange",
        )

    def _handle_entry_transfer(self):
        """Create enrollment and class group assignment for an incoming transfer."""
        if not self.entry_class_group:
            frappe.throw(_("Defina a Turma de Destino para transferência de entrada."))

        entry_class = frappe.db.get_value("Class Group", self.entry_class_group, "school_class")

        enrol = frappe.get_doc({
            "doctype": "Student Enrollment",
            "student": self.student,
            "academic_year": self.academic_year,
            "school_class": entry_class,
            "enrollment_date": self.transfer_date,
            "enrollment_status": "Activa",
            "enrollment_type": "Transferido",
        })
        enrol.flags.ignore_permissions = True
        enrol.insert()
        self.db_set("new_enrollment", enrol.name)

        assign = frappe.get_doc({
            "doctype": "Student Group Assignment",
            "student": self.student,
            "academic_year": self.academic_year,
            "enrollment": enrol.name,
            "school_class": entry_class,
            "class_group": self.entry_class_group,
            "assignment_date": self.transfer_date,
            "status": "Activa",
            "notes": _("Criado automaticamente pela Transferência {0}.").format(self.name),
        })
        assign.flags.ignore_permissions = True
        assign.insert()
        self.db_set("new_assignment", assign.name)

        _safe_set_student_status(self.student, "Activo")

        frappe.msgprint(
            _("Entrada registada. Inscrição <b>{0}</b> e alocação <b>{1}</b> criadas.").format(
                enrol.name, assign.name
            ),
            title=_("Entrada concluída"),
            indicator="green",
        )

    # ------------------------------------------------------------------
    # Cancel / revert actions
    # ------------------------------------------------------------------

    def _revert_internal_transfer(self):
        """Close the new assignment and reactivate the original."""
        if self.new_assignment and frappe.db.exists("Student Group Assignment", self.new_assignment):
            frappe.db.set_value("Student Group Assignment", self.new_assignment, "status", "Encerrada")

        if self.from_assignment and frappe.db.exists("Student Group Assignment", self.from_assignment):
            frappe.db.set_value("Student Group Assignment", self.from_assignment, "status", "Activa")

        frappe.msgprint(
            _("Transferência cancelada. A alocação original foi reactivada."),
            title=_("Transferência cancelada"),
            indicator="orange",
        )

    def _revert_exit_transfer(self):
        """Reactivate the assignment that was closed on exit."""
        if self.from_assignment and frappe.db.exists("Student Group Assignment", self.from_assignment):
            frappe.db.set_value("Student Group Assignment", self.from_assignment, "status", "Activa")

        # Reactivate the enrollment that was cancelled
        if self.new_enrollment and frappe.db.exists("Student Enrollment", self.new_enrollment):
            frappe.db.set_value("Student Enrollment", self.new_enrollment, "enrollment_status", "Activa")

        _safe_set_student_status(self.student, "Activo")

        frappe.msgprint(
            _("Saída cancelada. Alocação e inscrição reactivadas."),
            title=_("Cancelamento concluído"),
            indicator="orange",
        )

    def _revert_entry_transfer(self):
        """Close the assignment and cancel the enrollment created on entry."""
        if self.new_assignment and frappe.db.exists("Student Group Assignment", self.new_assignment):
            frappe.db.set_value("Student Group Assignment", self.new_assignment, "status", "Encerrada")

        if self.new_enrollment and frappe.db.exists("Student Enrollment", self.new_enrollment):
            frappe.db.set_value("Student Enrollment", self.new_enrollment, "enrollment_status", "Cancelada")

        _safe_set_student_status(self.student, "Transferido")

        frappe.msgprint(
            _("Entrada cancelada. Inscrição e alocação encerradas."),
            title=_("Cancelamento concluído"),
            indicator="orange",
        )
