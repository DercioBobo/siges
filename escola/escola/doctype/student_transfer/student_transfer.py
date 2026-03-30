import frappe
from frappe import _
from frappe.model.document import Document


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
        self._validate_has_active_sga()
        self._validate_not_duplicate()

    def on_submit(self):
        self._handle_exit()
        self.db_set("status", "Concluída")

    def on_cancel(self):
        self._revert_exit()
        self.db_set("status", "Cancelada")

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

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

    def _validate_not_duplicate(self):
        existing = frappe.db.get_value(
            "Student Transfer",
            {
                "student": self.student,
                "academic_year": self.academic_year,
                "status": "Concluída",
                "name": ("!=", self.name),
            },
            "name",
        )
        if existing:
            frappe.throw(
                _("Já existe uma transferência concluída para este aluno "
                  "neste ano lectivo: <b>{0}</b>.").format(existing),
                title=_("Transferência duplicada"),
            )

    # ------------------------------------------------------------------
    # Submit / cancel
    # ------------------------------------------------------------------

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

        for a in assignments:
            frappe.db.set_value("Student Group Assignment", a.name, "status", "Transferida")

        self.db_set("from_assignment", assignments[0].name)
        _safe_set_student_status(self.student, "Transferido")

        frappe.msgprint(
            _("{0} alocação(ões) encerrada(s). Aluno registado como transferido.").format(
                len(assignments)
            ),
            title=_("Saída registada"),
            indicator="orange",
        )

    def _revert_exit(self):
        if self.from_assignment and frappe.db.exists(
            "Student Group Assignment", self.from_assignment
        ):
            frappe.db.set_value(
                "Student Group Assignment", self.from_assignment, "status", "Activa"
            )
        _safe_set_student_status(self.student, "Activo")
        frappe.msgprint(
            _("Saída cancelada. Alocação reactivada."),
            title=_("Cancelamento concluído"),
            indicator="orange",
        )
