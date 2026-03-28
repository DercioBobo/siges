import frappe
from frappe import _
from frappe.model.document import Document


_INTERNAL = "Interna (Entre Turmas)"
_EXIT     = "Saída (Para Outra Escola)"
_ENTRY    = "Entrada (Outra Escola)"


def _safe_set_student_status(student, status):
    try:
        frappe.db.set_value("Student", student, "current_status", status, update_modified=False)
    except Exception:
        pass


class StudentTransfer(Document):
    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def validate(self):
        t = self.transfer_type or _INTERNAL
        if t == _INTERNAL:
            self._validate_origin_sga()
            self._validate_destination()
        elif t == _EXIT:
            self._validate_has_active_sga()
        elif t == _ENTRY:
            self._validate_entry()
        self._validate_not_duplicate()

    def on_submit(self):
        t = self.transfer_type or _INTERNAL
        if t == _INTERNAL:
            self._handle_internal()
        elif t == _EXIT:
            self._handle_exit()
        elif t == _ENTRY:
            self._handle_entry()
        self.db_set("status", "Concluída")

    def on_cancel(self):
        t = self.transfer_type or _INTERNAL
        if t == _INTERNAL:
            self._revert_internal()
        elif t == _EXIT:
            self._revert_exit()
        elif t == _ENTRY:
            self._revert_entry()
        self.db_set("status", "Cancelada")

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate_origin_sga(self):
        """Confirm the student has an active SGA in from_class_group."""
        if not self.from_class_group:
            return
        sga = frappe.db.get_value(
            "Student Group Assignment",
            {
                "student": self.student,
                "academic_year": self.academic_year,
                "class_group": self.from_class_group,
                "status": "Activa",
            },
            "name",
        )
        if not sga:
            frappe.throw(
                _("O aluno não tem uma alocação activa na Turma de Origem "
                  "<b>{0}</b> para o Ano Lectivo <b>{1}</b>.").format(
                    self.from_class_group, self.academic_year
                ),
                title=_("Alocação de origem não encontrada"),
            )
        self.from_assignment = sga

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
                {"class_group": self.to_class_group, "status": "Activa"},
            )
            if active_count >= cg.max_students:
                frappe.throw(
                    _("A Turma de Destino <b>{0}</b> já atingiu a capacidade máxima "
                      "de <b>{1}</b> alunos.").format(self.to_class_group, cg.max_students),
                    title=_("Capacidade esgotada"),
                )

    def _validate_has_active_sga(self):
        has = frappe.db.exists(
            "Student Group Assignment",
            {"student": self.student, "academic_year": self.academic_year, "status": "Activa"},
        )
        if not has:
            frappe.throw(
                _("O aluno <b>{0}</b> não tem alocações activas no Ano Lectivo <b>{1}</b>. "
                  "Não é possível registar uma saída.").format(self.student, self.academic_year),
                title=_("Sem alocação activa"),
            )

    def _validate_entry(self):
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
                {"class_group": self.entry_class_group, "status": "Activa"},
            )
            if active_count >= cg.max_students:
                frappe.throw(
                    _("A Turma de Destino <b>{0}</b> já atingiu a capacidade máxima "
                      "de <b>{1}</b> alunos.").format(self.entry_class_group, cg.max_students),
                    title=_("Capacidade esgotada"),
                )
        if frappe.db.exists(
            "Student Group Assignment",
            {"student": self.student, "academic_year": self.academic_year, "status": "Activa"},
        ):
            frappe.throw(
                _("O aluno <b>{0}</b> já tem uma alocação activa no Ano Lectivo <b>{1}</b>. "
                  "Utilize uma Transferência Interna.").format(self.student, self.academic_year),
                title=_("Alocação já existente"),
            )

    def _validate_not_duplicate(self):
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
    # Submit handlers
    # ------------------------------------------------------------------

    def _handle_internal(self):
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
                _("Não foi encontrada uma alocação activa na Turma de Origem <b>{0}</b>.").format(
                    self.from_class_group
                ),
                title=_("Alocação não encontrada"),
            )

        frappe.db.set_value("Student Group Assignment", old_name, "status", "Transferida")
        self.db_set("from_assignment", old_name)

        new_doc = frappe.get_doc({
            "doctype": "Student Group Assignment",
            "student": self.student,
            "academic_year": self.academic_year,
            "school_class": self.to_school_class,
            "class_group": self.to_class_group,
            "assignment_date": self.transfer_date,
            "status": "Activa",
            "notes": _("Criado automaticamente pela Transferência {0}.").format(self.name),
        })
        new_doc.flags.ignore_permissions = True
        new_doc.insert()
        self.db_set("new_assignment", new_doc.name)

        frappe.msgprint(
            _("Transferência concluída. Nova alocação criada: <b>{0}</b>.").format(new_doc.name),
            title=_("Transferência concluída"),
            indicator="green",
        )

    def _handle_exit(self):
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

        self.db_set("from_assignment", closed[0])
        _safe_set_student_status(self.student, "Transferido")

        frappe.msgprint(
            _("{0} alocação(ões) encerrada(s). Aluno registado como transferido.").format(len(closed)),
            title=_("Saída registada"),
            indicator="orange",
        )

    def _handle_entry(self):
        entry_class = frappe.db.get_value("Class Group", self.entry_class_group, "school_class")

        new_doc = frappe.get_doc({
            "doctype": "Student Group Assignment",
            "student": self.student,
            "academic_year": self.academic_year,
            "school_class": entry_class,
            "class_group": self.entry_class_group,
            "assignment_date": self.transfer_date,
            "status": "Activa",
            "notes": _("Criado automaticamente pela Transferência {0}.").format(self.name),
        })
        new_doc.flags.ignore_permissions = True
        new_doc.insert()
        self.db_set("new_assignment", new_doc.name)

        _safe_set_student_status(self.student, "Activo")

        frappe.msgprint(
            _("Entrada registada. Alocação <b>{0}</b> criada na Turma <b>{1}</b>.").format(
                new_doc.name, self.entry_class_group
            ),
            title=_("Entrada concluída"),
            indicator="green",
        )

    # ------------------------------------------------------------------
    # Cancel / revert
    # ------------------------------------------------------------------

    def _revert_internal(self):
        if self.new_assignment and frappe.db.exists("Student Group Assignment", self.new_assignment):
            frappe.db.set_value("Student Group Assignment", self.new_assignment, "status", "Encerrada")
        if self.from_assignment and frappe.db.exists("Student Group Assignment", self.from_assignment):
            frappe.db.set_value("Student Group Assignment", self.from_assignment, "status", "Activa")
        frappe.msgprint(
            _("Transferência cancelada. A alocação original foi reactivada."),
            title=_("Transferência cancelada"),
            indicator="orange",
        )

    def _revert_exit(self):
        if self.from_assignment and frappe.db.exists("Student Group Assignment", self.from_assignment):
            frappe.db.set_value("Student Group Assignment", self.from_assignment, "status", "Activa")
        _safe_set_student_status(self.student, "Activo")
        frappe.msgprint(
            _("Saída cancelada. Alocação reactivada."),
            title=_("Cancelamento concluído"),
            indicator="orange",
        )

    def _revert_entry(self):
        if self.new_assignment and frappe.db.exists("Student Group Assignment", self.new_assignment):
            frappe.db.set_value("Student Group Assignment", self.new_assignment, "status", "Encerrada")
        _safe_set_student_status(self.student, "Transferido")
        frappe.msgprint(
            _("Entrada cancelada. Alocação encerrada."),
            title=_("Cancelamento concluído"),
            indicator="orange",
        )
