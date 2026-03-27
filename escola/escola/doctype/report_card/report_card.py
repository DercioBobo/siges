import frappe
from frappe import _
from frappe.model.document import Document


class ReportCard(Document):
    def validate(self):
        self._validate_uniqueness()
        self._validate_no_duplicate_subjects()
        self._validate_grade_ranges()
        self._recalculate_summary()

    def _validate_uniqueness(self):
        existing = frappe.db.get_value(
            "Report Card",
            {
                "student": self.student,
                "academic_year": self.academic_year,
                "name": ("!=", self.name),
            },
            "name",
        )
        if existing:
            frappe.throw(
                _("Já existe um Boletim ({0}) para o aluno {1} no ano lectivo {2}.").format(
                    existing, self.student, self.academic_year
                )
            )

    def _validate_no_duplicate_subjects(self):
        seen = set()
        for row in self.report_card_rows:
            if row.subject in seen:
                frappe.throw(
                    _("A disciplina {0} está duplicada no Boletim.").format(row.subject)
                )
            seen.add(row.subject)

    def _validate_grade_ranges(self):
        for row in self.report_card_rows:
            if row.final_grade < 0 or row.final_grade > 20:
                frappe.throw(
                    _("A nota da disciplina {0} deve estar entre 0 e 20. Valor recebido: {1}.").format(
                        row.subject, row.final_grade
                    )
                )

    def _recalculate_summary(self):
        rows = self.report_card_rows or []
        self.total_subjects = len(rows)
        self.passed_subjects = sum(1 for r in rows if r.result == "Aprovado")
        self.failed_subjects = sum(1 for r in rows if r.result == "Reprovado")
        if rows:
            self.overall_average = round(
                sum(r.final_grade for r in rows) / len(rows), 1
            )
        else:
            self.overall_average = 0


@frappe.whitelist()
def load_assessment(doc_name):
    """
    Fetch Annual Assessment rows and Promotion decision for the student
    on this Report Card. Returns a dict that the JS side uses to populate
    the child table and summary fields.
    """
    doc = frappe.get_doc("Report Card", doc_name)

    if not doc.student or not doc.academic_year or not doc.class_group:
        frappe.throw(_("Preencha o Aluno, o Ano Lectivo e a Turma antes de carregar a avaliação."))

    annual = frappe.db.get_value(
        "Annual Assessment",
        {
            "class_group": doc.class_group,
            "academic_year": doc.academic_year,
        },
        "name",
    )
    if not annual:
        return {"error": "no_annual_assessment"}

    assessment_rows = frappe.get_all(
        "Annual Assessment Row",
        filters={"parent": annual, "student": doc.student},
        fields=["subject", "final_grade", "result", "remarks"],
        order_by="subject asc",
    )
    if not assessment_rows:
        return {"error": "no_student_data"}

    # Look up promotion decision for this student
    final_decision = None
    promotion = frappe.db.get_value(
        "Student Promotion",
        {
            "class_group": doc.class_group,
            "academic_year": doc.academic_year,
        },
        "name",
    )
    if promotion:
        decision = frappe.db.get_value(
            "Student Promotion Row",
            {"parent": promotion, "student": doc.student},
            "decision",
        )
        if decision:
            final_decision = decision

    primary_guardian = frappe.db.get_value("Student", doc.student, "primary_guardian")

    return {
        "rows": assessment_rows,
        "final_decision": final_decision,
        "primary_guardian": primary_guardian,
    }
