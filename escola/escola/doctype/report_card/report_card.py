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


# ---------------------------------------------------------------------------
# Core data builder (shared by load_assessment and auto-generation)
# ---------------------------------------------------------------------------

def _build_report_card_data(annual_name, student, school_class):
    """
    Re-run grade calculation for a single student and return structured data
    ready to populate a Report Card. Returns None if no data found.
    """
    from escola.escola.doctype.annual_assessment.annual_assessment import get_student_assessment_detail

    result = get_student_assessment_detail(annual_name, student)
    if result.get("error"):
        return None

    detail = result.get("detail") or {}
    if not detail:
        return None

    min_passing = float(
        frappe.db.get_value("School Class", school_class, "minimum_passing_grade")
        or frappe.db.get_single_value("School Settings", "minimum_passing_grade")
        or 10
    )

    rows = []
    for subject in sorted(detail.keys()):
        avg = detail[subject].get("avg")
        if avg is None:
            continue
        rows.append({
            "subject": subject,
            "final_grade": round(avg, 2),
            "result": "Aprovado" if avg >= min_passing else "Reprovado",
            "remarks": "",
        })

    annual_doc = frappe.get_doc("Annual Assessment", annual_name)

    final_decision = None
    promotion = frappe.db.get_value(
        "Student Promotion",
        {"class_group": annual_doc.class_group, "academic_year": annual_doc.academic_year},
        "name",
    )
    if promotion:
        decision = frappe.db.get_value(
            "Student Promotion Row",
            {"parent": promotion, "student": student},
            "decision",
        )
        if decision:
            final_decision = decision

    return {
        "rows": rows,
        "final_decision": final_decision,
        "primary_guardian": frappe.db.get_value("Student", student, "primary_guardian"),
        "academic_year": annual_doc.academic_year,
        "school_class": annual_doc.school_class,
        "class_group": annual_doc.class_group,
    }


# ---------------------------------------------------------------------------
# Manual load (called from form button)
# ---------------------------------------------------------------------------

@frappe.whitelist()
def load_assessment(doc_name):
    """Populate Report Card subject rows from live Grade Entry data."""
    doc = frappe.get_doc("Report Card", doc_name)

    if not doc.student or not doc.academic_year or not doc.class_group:
        frappe.throw(_("Preencha o Aluno, o Ano Lectivo e a Turma antes de carregar a avaliação."))

    annual_name = frappe.db.get_value(
        "Annual Assessment",
        {"class_group": doc.class_group, "academic_year": doc.academic_year},
        "name",
    )
    if not annual_name:
        return {"error": "no_annual_assessment"}

    data = _build_report_card_data(annual_name, doc.student, doc.school_class)
    if not data:
        return {"error": "no_student_data"}

    return {
        "rows": data["rows"],
        "final_decision": data["final_decision"],
        "primary_guardian": data["primary_guardian"],
    }


# ---------------------------------------------------------------------------
# Auto-generation: create or update Report Cards for all students
# ---------------------------------------------------------------------------

def generate_for_assessment(annual_name):
    """
    Create or update one Report Card per student in an Annual Assessment.
    Called from on_update hook and daily scheduler.
    """
    annual_doc = frappe.get_doc("Annual Assessment", annual_name)
    students = [row.student for row in (annual_doc.assessment_rows or [])]

    if not students:
        return

    created, updated, skipped = 0, 0, 0

    for student in students:
        try:
            data = _build_report_card_data(annual_name, student, annual_doc.school_class)
            if not data or not data["rows"]:
                skipped += 1
                continue

            existing = frappe.db.get_value(
                "Report Card",
                {"student": student, "academic_year": annual_doc.academic_year},
                "name",
            )

            if existing:
                rc = frappe.get_doc("Report Card", existing)
                rc.set("report_card_rows", [])
                for row in data["rows"]:
                    rc.append("report_card_rows", row)
                if data["final_decision"]:
                    rc.final_decision = data["final_decision"]
                if data["primary_guardian"] and not rc.primary_guardian:
                    rc.primary_guardian = data["primary_guardian"]
                rc.save(ignore_permissions=True)
                updated += 1
            else:
                rc = frappe.new_doc("Report Card")
                rc.student = student
                rc.academic_year = annual_doc.academic_year
                rc.school_class = annual_doc.school_class
                rc.class_group = annual_doc.class_group
                rc.primary_guardian = data["primary_guardian"]
                rc.final_decision = data["final_decision"]
                for row in data["rows"]:
                    rc.append("report_card_rows", row)
                rc.insert(ignore_permissions=True)
                created += 1

        except Exception:
            frappe.log_error(
                title=f"Escola — falha ao gerar Boletim para {student}",
                message=frappe.get_traceback(),
            )
            skipped += 1

    frappe.db.commit()
    return {"created": created, "updated": updated, "skipped": skipped}


def generate_for_assessment_hook(doc, method=None):
    """Doc event wrapper — called by hooks.py on Annual Assessment on_update."""
    if not (doc.assessment_rows):
        return
    try:
        generate_for_assessment(doc.name)
    except Exception:
        frappe.log_error(
            title=f"Escola — falha ao gerar Boletins para {doc.name}",
            message=frappe.get_traceback(),
        )


def refresh_all_report_cards():
    """
    Daily scheduler: refresh all Report Cards from current Grade Entry data.
    Only processes assessments that have rows (i.e. have been calculated).
    """
    assessments = frappe.get_all(
        "Annual Assessment",
        filters={},
        fields=["name"],
    )
    for a in assessments:
        try:
            # Skip assessments with no rows
            has_rows = frappe.db.exists("Annual Assessment Row", {"parent": a.name})
            if not has_rows:
                continue
            generate_for_assessment(a.name)
        except Exception:
            frappe.log_error(
                title=f"Escola — falha ao actualizar Boletins para {a.name}",
                message=frappe.get_traceback(),
            )
