import frappe
from frappe import _
from frappe.model.document import Document
from escola.escola.doctype.class_curriculum.class_curriculum import get_curriculum_subjects


@frappe.whitelist()
def get_grade_entry_students(class_group, academic_year, subject=None):
    """Return rows to load into a Grade Entry.

    Single-subject mode (subject given): students × 1 subject.
    Multi-subject mode (subject omitted): students × all non-specialist subjects
    from the active curriculum. This is intended for primary-school homeroom
    teachers who teach all subjects in one session.
    """
    students = frappe.get_all(
        "Student Group Assignment",
        filters={
            "class_group": class_group,
            "academic_year": academic_year,
            "status": "Activa",
        },
        fields=["student"],
        order_by="student asc",
    )
    if not students:
        return {"error": "no_students"}

    if subject:
        return [{"student": s.student, "subject": subject} for s in students]

    # Multi-subject: load non-specialist subjects from the active curriculum
    curriculum = get_curriculum_subjects(class_group)
    if not curriculum:
        return {"error": "no_subjects"}

    subject_names = [sl.subject for sl in curriculum]
    specialist_records = frappe.get_all(
        "Subject",
        filters=[["name", "in", subject_names]],
        fields=["name", "is_specialist"],
    )
    specialist_set = {r.name for r in specialist_records if r.is_specialist}
    target_subjects = [s for s in subject_names if s not in specialist_set] or subject_names

    rows = []
    for student in students:
        for subj in target_subjects:
            rows.append({"student": student.student, "subject": subj})
    return rows


class GradeEntry(Document):
    def validate(self):
        self._validate_term_belongs_to_year()
        self._validate_class_group_compatibility()
        self._validate_rows_not_empty()
        self._validate_no_duplicate_rows()
        self._validate_score_ranges()
        self._compute_approved()
        self._calculate_class_summary()

    # ------------------------------------------------------------------
    # Header validations
    # ------------------------------------------------------------------

    def _validate_term_belongs_to_year(self):
        if not (self.academic_term and self.academic_year):
            return
        year = frappe.db.get_value("Academic Term", self.academic_term, "academic_year")
        if year != self.academic_year:
            frappe.throw(
                _("O Período <b>{0}</b> pertence ao Ano Lectivo <b>{1}</b>, "
                  "não a <b>{2}</b>.").format(
                    self.academic_term, year, self.academic_year
                ),
                title=_("Período incompatível"),
            )

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
                  "não a <b>{2}</b>.").format(
                    self.class_group, cg.academic_year, self.academic_year
                ),
                title=_("Turma incompatível"),
            )
        if self.school_class and cg.school_class != self.school_class:
            frappe.throw(
                _("A Turma <b>{0}</b> pertence à Classe <b>{1}</b>, "
                  "não a <b>{2}</b>.").format(
                    self.class_group, cg.school_class, self.school_class
                ),
                title=_("Turma incompatível"),
            )

    # ------------------------------------------------------------------
    # Row validations
    # ------------------------------------------------------------------

    def _validate_rows_not_empty(self):
        if not self.grade_rows:
            frappe.throw(
                _("A Pauta não pode estar vazia. "
                  "Use o botão <b>Carregar Alunos</b> para preencher a tabela."),
                title=_("Tabela vazia"),
            )

    def _validate_no_duplicate_rows(self):
        seen = set()
        for row in self.grade_rows:
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

    def _validate_score_ranges(self):
        max_s = float(self.max_score or 20)
        for row in self.grade_rows:
            if row.is_absent or row.score is None:
                continue
            if row.score < 0 or row.score > max_s:
                frappe.throw(
                    _("A nota <b>{0}</b> do aluno <b>{1}</b> / disciplina <b>{2}</b> "
                      "está fora do intervalo permitido (0 – {3}).").format(
                        row.score, row.student, row.subject, max_s
                    ),
                    title=_("Nota fora do intervalo"),
                )

    # ------------------------------------------------------------------
    # Calculations
    # ------------------------------------------------------------------

    def _compute_approved(self):
        min_pass = 10.0
        if self.school_class:
            val = frappe.db.get_value("School Class", self.school_class, "minimum_passing_grade")
            if val:
                min_pass = float(val)
        for row in self.grade_rows:
            if row.is_absent:
                row.is_approved = 0
                row.score = None
            elif row.score is not None:
                row.is_approved = 1 if row.score >= min_pass else 0
            else:
                row.is_approved = 0

    def _calculate_class_summary(self):
        scores = [
            row.score for row in self.grade_rows
            if not row.is_absent and row.score is not None
        ]
        self.class_average = round(sum(scores) / len(scores), 2) if scores else 0
        self.total_approved = sum(1 for row in self.grade_rows if row.is_approved)
        self.total_failed = sum(
            1 for row in self.grade_rows
            if not row.is_approved and not row.is_absent and row.score is not None
        )
