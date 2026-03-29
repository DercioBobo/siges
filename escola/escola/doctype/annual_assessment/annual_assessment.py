import frappe
from frappe import _
from frappe.model.document import Document


@frappe.whitelist()
def calculate_assessment(doc_name):
    """
    Compute final grades for all students in a class group.

    Algorithm:
    1. Fetch Academic Terms for the year ordered by start date → positional mapping T1/T2/T3.
    2. For each Grade Entry (class_group, academic_year), collect rows with valid scores.
       Multiple Grade Entries in the same term (e.g. Teste 1 + Teste 2) are averaged.
    3. Per (student, subject): term_N_average = average of all scores in that term.
       final_grade = simple average of available term averages.
    4. Compare against School Class minimum_passing_grade.
    """
    doc = frappe.get_doc("Annual Assessment", doc_name)

    terms = frappe.get_all(
        "Academic Term",
        filters={"academic_year": doc.academic_year},
        fields=["name", "term_start_date"],
        order_by="term_start_date asc, name asc",
    )
    if not terms:
        return {"error": "no_terms"}

    term_position = {t.name: idx + 1 for idx, t in enumerate(terms)}

    min_passing = float(
        frappe.db.get_value("School Class", doc.school_class, "minimum_passing_grade")
        or frappe.db.get_single_value("School Settings", "minimum_passing_grade")
        or 10
    )

    grade_entries = frappe.get_all(
        "Grade Entry",
        filters={
            "class_group": doc.class_group,
            "academic_year": doc.academic_year,
            "docstatus": ("!=", 2),
        },
        fields=["name", "academic_term"],
    )
    if not grade_entries:
        return {"error": "no_grade_entries"}

    # data[student][subject][term_pos] = [score, ...]
    data: dict = {}
    for entry in grade_entries:
        pos = term_position.get(entry.academic_term)
        if pos is None:
            continue
        rows = frappe.get_all(
            "Grade Entry Row",
            filters={"parent": entry.name, "is_absent": 0},
            fields=["student", "subject", "score"],
        )
        for row in rows:
            if row.score is None:
                continue
            (
                data
                .setdefault(row.student, {})
                .setdefault(row.subject, {})
                .setdefault(pos, [])
                .append(float(row.score))
            )

    if not data:
        return {"error": "no_grades"}

    result_rows = []
    max_terms = len(terms)

    for student in sorted(data):
        for subject in sorted(data[student]):
            term_avgs = {
                pos: round(sum(vals) / len(vals), 2)
                for pos, vals in data[student][subject].items()
            }

            t1 = term_avgs.get(1)
            t2 = term_avgs.get(2) if max_terms >= 2 else None
            t3 = term_avgs.get(3) if max_terms >= 3 else None

            present = list(term_avgs.values())
            final_grade = round(sum(present) / len(present), 2) if present else 0.0
            result = "Aprovado" if final_grade >= min_passing else "Reprovado"

            result_rows.append({
                "student": student,
                "subject": subject,
                "term_1_average": t1,
                "term_2_average": t2,
                "term_3_average": t3,
                "final_grade": final_grade,
                "result": result,
                "remarks": "",
            })

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
        max_grade = float(
            frappe.db.get_single_value("School Settings", "grading_scale_max") or 20
        )
        seen = set()
        for row in self.assessment_rows:
            if row.final_grade is not None and (
                row.final_grade < 0 or row.final_grade > max_grade
            ):
                frappe.throw(
                    _("A nota final <b>{0}</b> para o aluno <b>{1}</b> / "
                      "disciplina <b>{2}</b> está fora do intervalo 0–{3}.").format(
                        row.final_grade, row.student, row.subject, max_grade
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
