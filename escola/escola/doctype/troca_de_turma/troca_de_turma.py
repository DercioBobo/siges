import frappe
from frappe import _
from frappe.model.document import Document


class TrocaDeTurma(Document):
    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def validate(self):
        self._validate_different_groups()
        self._validate_same_year()
        self._validate_student_in_origin()
        self._validate_destination()
        self._validate_cross_class_reason()
        self._validate_not_duplicate()

    def on_submit(self):
        self._execute_transfer()
        self.db_set("status", "Concluída")

    def on_cancel(self):
        self._revert_transfer()
        self.db_set("status", "Cancelada")

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate_different_groups(self):
        if self.from_class_group and self.to_class_group:
            if self.from_class_group == self.to_class_group:
                frappe.throw(
                    _("A Turma de Destino não pode ser igual à Turma de Origem."),
                    title=_("Destino inválido"),
                )

    def _validate_same_year(self):
        if not self.to_class_group or not self.academic_year:
            return
        dest_year = frappe.db.get_value("Class Group", self.to_class_group, "academic_year")
        if dest_year and dest_year != self.academic_year:
            frappe.throw(
                _("A Turma de Destino <b>{0}</b> pertence ao Ano Lectivo <b>{1}</b>, "
                  "não ao Ano Lectivo <b>{2}</b>.").format(
                    self.to_class_group, dest_year, self.academic_year
                ),
                title=_("Ano lectivo incompatível"),
            )

    def _validate_student_in_origin(self):
        if not self.from_class_group or not self.student:
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

    def _validate_destination(self):
        if not self.to_class_group:
            return
        cg = frappe.db.get_value(
            "Class Group",
            self.to_class_group,
            ["is_active", "max_students"],
            as_dict=True,
        )
        if not cg:
            return
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

    def _validate_cross_class_reason(self):
        if not self.from_class_group or not self.to_class_group:
            return
        from_sc = frappe.db.get_value("Class Group", self.from_class_group, "school_class")
        to_sc   = frappe.db.get_value("Class Group", self.to_class_group,   "school_class")
        if from_sc and to_sc and from_sc != to_sc and not self.reason:
            frappe.throw(
                _("A turma de destino pertence a uma classe diferente ({0} → {1}). "
                  "O campo <b>Motivo da Troca</b> é obrigatório neste caso.").format(
                    from_sc, to_sc
                ),
                title=_("Motivo obrigatório"),
            )

    def _validate_not_duplicate(self):
        existing = frappe.db.get_value(
            "Troca de Turma",
            {
                "student": self.student,
                "academic_year": self.academic_year,
                "from_class_group": self.from_class_group,
                "to_class_group": self.to_class_group,
                "status": "Concluída",
                "name": ("!=", self.name),
            },
            "name",
        )
        if existing:
            frappe.throw(
                _("Já existe uma Troca de Turma concluída para este aluno "
                  "com o mesmo percurso neste ano lectivo: <b>{0}</b>.").format(existing),
                title=_("Troca duplicada"),
            )

    # ------------------------------------------------------------------
    # Submit / cancel
    # ------------------------------------------------------------------

    def _execute_transfer(self):
        old_sga = frappe.db.get_value(
            "Student Group Assignment",
            {
                "student": self.student,
                "academic_year": self.academic_year,
                "class_group": self.from_class_group,
                "status": "Activa",
            },
            "name",
        )
        if not old_sga:
            frappe.throw(
                _("Não foi encontrada uma alocação activa na Turma de Origem <b>{0}</b>.").format(
                    self.from_class_group
                ),
                title=_("Alocação não encontrada"),
            )

        frappe.db.set_value("Student Group Assignment", old_sga, "status", "Transferida")
        self.db_set("from_assignment", old_sga)

        to_sc = frappe.db.get_value("Class Group", self.to_class_group, "school_class")
        new_sga = frappe.get_doc({
            "doctype": "Student Group Assignment",
            "student": self.student,
            "academic_year": self.academic_year,
            "school_class": to_sc,
            "class_group": self.to_class_group,
            "assignment_date": self.effective_date,
            "status": "Activa",
            "notes": _("Criada automaticamente pela Troca de Turma {0}.").format(self.name),
        })
        new_sga.flags.ignore_permissions = True
        new_sga.insert()
        self.db_set("new_assignment", new_sga.name)

        frappe.msgprint(
            _("Troca concluída. O aluno foi movido para <b>{0}</b>.").format(self.to_class_group),
            title=_("Troca de Turma concluída"),
            indicator="green",
        )

    def _revert_transfer(self):
        if self.new_assignment and frappe.db.exists(
            "Student Group Assignment", self.new_assignment
        ):
            frappe.db.set_value(
                "Student Group Assignment", self.new_assignment, "status", "Encerrada"
            )
        if self.from_assignment and frappe.db.exists(
            "Student Group Assignment", self.from_assignment
        ):
            frappe.db.set_value(
                "Student Group Assignment", self.from_assignment, "status", "Activa"
            )
        frappe.msgprint(
            _("Troca cancelada. O aluno foi recolocado na Turma de Origem <b>{0}</b>.").format(
                self.from_class_group
            ),
            title=_("Troca cancelada"),
            indicator="orange",
        )
