import frappe
from frappe import _
from frappe.model.document import Document


@frappe.whitelist()
def get_students_for_renewal(class_group, academic_year):
    """Return active students in class_group with their current renewal status."""
    sgas = frappe.get_all(
        "Student Group Assignment",
        filters={
            "class_group": class_group,
            "academic_year": academic_year,
            "status": "Activa",
        },
        fields=["student"],
        order_by="student asc",
    )

    result = []
    for sga in sgas:
        s = frappe.db.get_value(
            "Student",
            sga.student,
            ["student_code", "full_name", "financial_status", "current_status"],
            as_dict=True,
        )
        if not s:
            continue
        # Check if already marked in class group student table
        cgs = frappe.db.get_value(
            "Class Group Student",
            {"parent": class_group, "student": sga.student},
            ["renovacao", "data_renovacao", "renovacao_ref"],
            as_dict=True,
        )
        result.append(
            {
                "student": sga.student,
                "student_code": s.student_code or "",
                "full_name": s.full_name or sga.student,
                "financial_status": s.financial_status or "",
                "current_status": s.current_status or "",
                "renovacao": (cgs.renovacao if cgs else "") or "",
            }
        )

    result.sort(key=lambda x: x["full_name"])
    return result


class RenovacaoDeMatricula(Document):
    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def validate(self):
        self._validate_years()
        self._validate_not_duplicate()
        self._compute_totals()

    def on_submit(self):
        self._execute_renewal()
        self.db_set("status", "Concluída")

    def on_cancel(self):
        self._revert_renewal()
        self.db_set("status", "Cancelada")

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate_years(self):
        if self.academic_year == self.target_academic_year:
            frappe.throw(
                _("O Ano Lectivo de Destino deve ser diferente do Ano Lectivo de Origem."),
                title=_("Anos lectivos inválidos"),
            )

    def _validate_not_duplicate(self):
        existing = frappe.db.get_value(
            "Renovacao de Matricula",
            {
                "class_group": self.class_group,
                "academic_year": self.academic_year,
                "target_academic_year": self.target_academic_year,
                "status": "Concluída",
                "name": ("!=", self.name),
            },
            "name",
        )
        if existing:
            frappe.throw(
                _(
                    "Já existe uma Renovacao de Matricula concluída para esta turma "
                    "neste percurso de anos: <b>{0}</b>."
                ).format(existing),
                title=_("Renovação duplicada"),
            )

    def _compute_totals(self):
        rows = self.renovation_students or []
        self.total_students = len(rows)
        self.total_renewed = sum(1 for r in rows if r.renovacao == "Sim")
        self.total_not_renewed = sum(1 for r in rows if r.renovacao == "Não")

    # ------------------------------------------------------------------
    # Submit
    # ------------------------------------------------------------------

    def _execute_renewal(self):
        today = frappe.utils.today()
        created_sgas = []

        for row in self.renovation_students:
            if not row.renovacao:
                continue  # skip rows not yet decided

            # Update Class Group Student record
            cgs_name = frappe.db.get_value(
                "Class Group Student",
                {"parent": self.class_group, "student": row.student},
                "name",
            )
            if cgs_name:
                frappe.db.set_value(
                    "Class Group Student",
                    cgs_name,
                    {
                        "renovacao": row.renovacao,
                        "data_renovacao": self.renewal_date or today,
                        "renovacao_ref": self.name,
                    },
                )

            if row.renovacao != "Sim":
                continue

            # Create SGA for target year if a target turma is known
            target_cg = row.target_class_group or self.target_class_group
            if not target_cg:
                continue

            # Skip if SGA already exists
            if frappe.db.exists(
                "Student Group Assignment",
                {
                    "student": row.student,
                    "academic_year": self.target_academic_year,
                    "class_group": target_cg,
                    "status": "Activa",
                },
            ):
                continue

            to_sc = frappe.db.get_value("Class Group", target_cg, "school_class")
            new_sga = frappe.get_doc(
                {
                    "doctype": "Student Group Assignment",
                    "student": row.student,
                    "academic_year": self.target_academic_year,
                    "school_class": to_sc,
                    "class_group": target_cg,
                    "assignment_date": self.renewal_date or today,
                    "status": "Activa",
                    "notes": _(
                        "Criada automaticamente pela Renovacao de Matricula {0}."
                    ).format(self.name),
                }
            )
            new_sga.flags.ignore_permissions = True
            new_sga.insert()
            created_sgas.append(target_cg)

        renewed = self.total_renewed or 0
        not_renewed = self.total_not_renewed or 0
        msg_parts = [
            _("<b>{0}</b> aluno(s) marcado(s) para renovação.").format(renewed),
            _("<b>{0}</b> aluno(s) não renova(m).").format(not_renewed),
        ]
        if created_sgas:
            msg_parts.append(
                _("{0} alocação(ões) criada(s) para <b>{1}</b>.").format(
                    len(created_sgas), self.target_academic_year
                )
            )
        frappe.msgprint(
            "<br>".join(msg_parts),
            title=_("Renovação concluída"),
            indicator="green",
        )

    # ------------------------------------------------------------------
    # Cancel
    # ------------------------------------------------------------------

    def _revert_renewal(self):
        for row in self.renovation_students:
            if not row.renovacao:
                continue

            # Reset Class Group Student record
            cgs_name = frappe.db.get_value(
                "Class Group Student",
                {
                    "parent": self.class_group,
                    "student": row.student,
                    "renovacao_ref": self.name,
                },
                "name",
            )
            if cgs_name:
                frappe.db.set_value(
                    "Class Group Student",
                    cgs_name,
                    {"renovacao": "", "data_renovacao": None, "renovacao_ref": ""},
                )

            if row.renovacao != "Sim":
                continue

            # Deactivate any SGA created by this renewal
            target_cg = row.target_class_group or self.target_class_group
            if not target_cg:
                continue

            sga_name = frappe.db.get_value(
                "Student Group Assignment",
                {
                    "student": row.student,
                    "academic_year": self.target_academic_year,
                    "class_group": target_cg,
                    "status": "Activa",
                },
                "name",
            )
            if sga_name:
                notes = frappe.db.get_value("Student Group Assignment", sga_name, "notes") or ""
                if self.name in notes:
                    frappe.db.set_value(
                        "Student Group Assignment", sga_name, "status", "Encerrada"
                    )

        frappe.msgprint(
            _("Renovação cancelada. Marcações de renovação revertidas."),
            title=_("Renovação cancelada"),
            indicator="orange",
        )
