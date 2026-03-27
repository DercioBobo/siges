import frappe
from frappe import _
from frappe.model.document import Document


@frappe.whitelist()
def calculate_assessment(doc_name):
    """
    Compute final grades for all students in a class group.

    Algorithm:
    1. Load Assessment Scheme weight map: {evaluation_type: weight}
    2. Collect all Grade Entry rows for (academic_year, class_group)
       grouped as grade_data[student][subject][evaluation_type] = [grades]
    3. For each student+subject:
       a. Average grades per evaluation_type
       b. Build weighted sum using only components that have data
          (normalized so missing components don't penalise the student)
    4. Compare final_grade against School Class minimum_passing_grade
    5. Return list of row dicts for the client to populate the table
    """
    doc = frappe.get_doc("Annual Assessment", doc_name)

    # --- scheme weights --------------------------------------------------
    scheme = frappe.get_doc("Assessment Scheme", doc.assessment_scheme)
    weight_map = {c.evaluation_type: float(c.weight) for c in scheme.components}

    # --- minimum passing grade -------------------------------------------
    min_passing = (
        frappe.db.get_value(
            "School Class", doc.school_class, "minimum_passing_grade"
        )
        or 10
    )

    # --- collect grade rows from all Grade Entry documents ---------------
    grade_entries = frappe.get_all(
        "Grade Entry",
        filters={
            "academic_year": doc.academic_year,
            "class_group": doc.class_group,
        },
        fields=["name", "evaluation_type"],
    )

    if not grade_entries:
        return {"error": "no_grade_entries"}

    # grade_data[student][subject][evaluation_type] = [grade, ...]
    grade_data: dict = {}
    for entry in grade_entries:
        rows = frappe.get_all(
            "Grade Entry Row",
            filters={"parent": entry.name},
            fields=["student", "subject", "grade"],
        )
        for row in rows:
            if row.grade is None:
                continue
            (
                grade_data
                .setdefault(row.student, {})
                .setdefault(row.subject, {})
                .setdefault(entry.evaluation_type, [])
                .append(float(row.grade))
            )

    if not grade_data:
        return {"error": "no_grades"}

    # --- compute weighted final grade per student+subject ----------------
    result_rows = []
    for student in sorted(grade_data):
        for subject in sorted(grade_data[student]):
            eval_grades = grade_data[student][subject]

            # Average within each evaluation type
            component_avgs = {
                et: sum(grades) / len(grades)
                for et, grades in eval_grades.items()
            }

            # Weights for present components only, then normalize to 100
            present_weight_sum = sum(
                weight_map.get(et, 0) for et in component_avgs
            )

            if present_weight_sum == 0:
                final_grade = 0.0
            else:
                final_grade = sum(
                    avg * (weight_map.get(et, 0) / present_weight_sum)
                    for et, avg in component_avgs.items()
                )

            final_grade = round(final_grade, 2)
            result = "Aprovado" if final_grade >= float(min_passing) else "Reprovado"

            result_rows.append(
                {
                    "student": student,
                    "subject": subject,
                    "final_grade": final_grade,
                    "result": result,
                    "remarks": "",
                }
            )

    return result_rows


class AnnualAssessment(Document):
    def validate(self):
        self._validate_class_group_compatibility()
        self._validate_uniqueness()
        self._validate_row_integrity()

    def _validate_class_group_compatibility(self):
        if not self.class_group:
            return
        cg = frappe.db.get_value(
            "Class Group",
            self.class_group,
            ["academic_year", "school_class"],
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

    def _validate_uniqueness(self):
        existing = frappe.db.get_value(
            "Annual Assessment",
            {
                "academic_year": self.academic_year,
                "class_group": self.class_group,
                "name": ("!=", self.name),
            },
            "name",
        )
        if existing:
            frappe.throw(
                _("Já existe uma Avaliação Anual para a Turma <b>{0}</b> "
                  "no Ano Lectivo <b>{1}</b>: <b>{2}</b>.").format(
                    self.class_group, self.academic_year, existing
                ),
                title=_("Avaliação duplicada"),
            )

    def _validate_row_integrity(self):
        seen = set()
        for row in self.assessment_rows:
            if row.final_grade is not None and (
                row.final_grade < 0 or row.final_grade > 20
            ):
                frappe.throw(
                    _("A nota final <b>{0}</b> para o aluno <b>{1}</b> / "
                      "disciplina <b>{2}</b> está fora do intervalo 0–20.").format(
                        row.final_grade, row.student, row.subject
                    ),
                    title=_("Nota fora do intervalo"),
                )
            key = (row.student, row.subject)
            if key in seen:
                frappe.throw(
                    _("A combinação Aluno <b>{0}</b> + Disciplina <b>{1}</b> "
                      "aparece mais de uma vez na tabela.").format(
                        row.student, row.subject
                    ),
                    title=_("Linha duplicada"),
                )
            seen.add(key)
