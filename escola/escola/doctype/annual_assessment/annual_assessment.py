import frappe
from frappe import _
from frappe.model.document import Document
from escola.escola.doctype.term_attendance.term_attendance import get_annual_absences


@frappe.whitelist()
def get_students_for_assessment(class_group):
    """Return active students in a class group."""
    sgas = frappe.db.get_all(
        "Student Group Assignment",
        filters={"class_group": class_group, "status": "Activa"},
        fields=["student"],
        order_by="student asc",
    )
    return [s.student for s in sgas]


@frappe.whitelist()
def calculate_assessment(doc_name):
    """
    Compute per-student overall averages from Grade Entry data.

    Returns:
        {
            "rows":    [ {student, term_1_average, term_2_average, term_3_average,
                          final_grade, total_absences, result}, ... ],
            "details": { student: { subject: {t1, t2, t3, avg}, ... }, ... },
            "terms":   ["T1", "T2", "T3"]   (labels of present terms)
        }
    """
    doc = frappe.get_doc("Annual Assessment", doc_name)

    terms = frappe.get_all(
        "Academic Term",
        filters={"academic_year": doc.academic_year},
        fields=["name", "term_name", "start_date"],
        order_by="start_date asc, name asc",
    )
    if not terms:
        return {"error": "no_terms"}

    # Position map: term_name → 1/2/3
    term_position = {t.name: idx + 1 for idx, t in enumerate(terms)}
    term_labels   = [t.term_name or t.name for t in terms]

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

    absences = get_annual_absences(doc.class_group, doc.academic_year)
    abs_threshold = int(
        frappe.db.get_single_value("School Settings", "max_absences_threshold") or 0
    )
    max_terms = len(terms)

    result_rows = []
    details = {}

    for student in sorted(data):
        student_abs = absences.get(student, {})
        total_abs   = student_abs.get("total", 0)

        # Per subject: average per term
        subject_term_avgs = {}  # subject → {pos: avg}
        for subject, term_scores in data[student].items():
            subject_term_avgs[subject] = {
                pos: round(sum(vals) / len(vals), 2)
                for pos, vals in term_scores.items()
            }

        # Per term: mean of all subject averages
        term_avgs = {}  # pos → mean across subjects
        for pos in range(1, max_terms + 1):
            vals = [
                subject_term_avgs[subj][pos]
                for subj in subject_term_avgs
                if pos in subject_term_avgs[subj]
            ]
            if vals:
                term_avgs[pos] = round(sum(vals) / len(vals), 2)

        all_term_avgs = list(term_avgs.values())
        final_grade   = round(sum(all_term_avgs) / len(all_term_avgs), 2) if all_term_avgs else 0.0
        result        = "Aprovado" if final_grade >= min_passing else "Reprovado"

        result_rows.append({
            "student":        student,
            "term_1_average": term_avgs.get(1),
            "term_2_average": term_avgs.get(2) if max_terms >= 2 else None,
            "term_3_average": term_avgs.get(3) if max_terms >= 3 else None,
            "final_grade":    final_grade,
            "total_absences": total_abs,
            "result":         result,
        })

        # Details for HTML: subject → {t1, t2, t3, avg}
        subject_details = {}
        for subject, term_avgs_s in subject_term_avgs.items():
            s_avgs = list(term_avgs_s.values())
            subject_details[subject] = {
                "t1":  term_avgs_s.get(1),
                "t2":  term_avgs_s.get(2),
                "t3":  term_avgs_s.get(3),
                "avg": round(sum(s_avgs) / len(s_avgs), 2) if s_avgs else None,
            }
        details[student] = subject_details

    return {"rows": result_rows, "details": details, "terms": term_labels}


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
                "class_group":   self.class_group,
                "name":          ("!=", self.name),
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
                    _("A média geral <b>{0}</b> para o aluno <b>{1}</b> "
                      "está fora do intervalo 0–{2}.").format(
                        row.final_grade, row.student, max_grade
                    ),
                    title=_("Nota fora do intervalo"),
                )
            if row.student in seen:
                frappe.throw(
                    _("O aluno <b>{0}</b> aparece mais de uma vez na tabela.").format(
                        row.student
                    ),
                    title=_("Aluno duplicado"),
                )
            seen.add(row.student)
