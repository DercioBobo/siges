import frappe
from frappe import _
from frappe.model.document import Document


@frappe.whitelist()
def get_students_and_subjects(class_group, academic_year):
    """Return Cartesian product of active students × active subjects for a class group.

    Called by the client-side "Carregar Alunos e Disciplinas" button.
    Returns a list of dicts: {student, subject, teacher}.
    """
    student_assignments = frappe.get_all(
        "Student Group Assignment",
        filters={
            "class_group": class_group,
            "academic_year": academic_year,
            "status": "Activa",
        },
        fields=["student"],
        order_by="student asc",
    )

    subject_assignments = frappe.get_all(
        "Class Subject Assignment",
        filters={
            "class_group": class_group,
            "academic_year": academic_year,
            "is_active": 1,
        },
        fields=["subject", "teacher"],
        order_by="subject asc",
    )

    if not student_assignments:
        return {"error": "no_students"}
    if not subject_assignments:
        return {"error": "no_subjects"}

    rows = []
    for sa in student_assignments:
        for ca in subject_assignments:
            rows.append(
                {
                    "student": sa.student,
                    "subject": ca.subject,
                    "teacher": ca.teacher or None,
                }
            )
    return rows


class GradeEntry(Document):
    def validate(self):
        self._validate_academic_term_belongs_to_year()
        self._validate_class_group_compatibility()
        self._validate_uniqueness()
        self._validate_rows_not_empty()
        self._validate_no_duplicate_rows()
        self._validate_grade_range()
        self._validate_subjects_assigned()

    # ------------------------------------------------------------------
    # Header validations
    # ------------------------------------------------------------------

    def _validate_academic_term_belongs_to_year(self):
        if not (self.academic_term and self.academic_year):
            return
        year = frappe.db.get_value("Academic Term", self.academic_term, "academic_year")
        if year != self.academic_year:
            frappe.throw(
                _("O Período Académico <b>{0}</b> pertence ao Ano Lectivo "
                  "<b>{1}</b>, não ao Ano Lectivo <b>{2}</b>.").format(
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
            ["academic_year", "school_class", "is_active"],
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
                title=_("Turma incompatível"),
            )

    def _validate_uniqueness(self):
        existing = frappe.db.get_value(
            "Grade Entry",
            {
                "academic_year": self.academic_year,
                "academic_term": self.academic_term,
                "class_group": self.class_group,
                "evaluation_type": self.evaluation_type,
                "name": ("!=", self.name),
            },
            "name",
        )
        if existing:
            frappe.throw(
                _("Já existe uma Pauta de Notas para a Turma <b>{0}</b>, "
                  "Período <b>{1}</b> e Tipo de Avaliação <b>{2}</b>: "
                  "<b>{3}</b>.").format(
                    self.class_group,
                    self.academic_term,
                    self.evaluation_type,
                    existing,
                ),
                title=_("Pauta duplicada"),
            )

    # ------------------------------------------------------------------
    # Row validations
    # ------------------------------------------------------------------

    def _validate_rows_not_empty(self):
        if not self.grade_rows:
            frappe.throw(
                _("A Pauta de Notas não pode estar vazia. "
                  "Utilize o botão <b>Carregar Alunos e Disciplinas</b> "
                  "para preencher a tabela."),
                title=_("Tabela vazia"),
            )

    def _validate_no_duplicate_rows(self):
        seen = set()
        for row in self.grade_rows:
            key = (row.student, row.subject)
            if key in seen:
                frappe.throw(
                    _("A combinação Aluno <b>{0}</b> + Disciplina <b>{1}</b> "
                      "aparece mais de uma vez na tabela de notas.").format(
                        row.student, row.subject
                    ),
                    title=_("Linha duplicada"),
                )
            seen.add(key)

    def _validate_grade_range(self):
        for row in self.grade_rows:
            if row.grade is None:
                continue
            if row.grade < 0 or row.grade > 20:
                frappe.throw(
                    _("A nota <b>{0}</b> na linha do aluno <b>{1}</b> "
                      "/ disciplina <b>{2}</b> está fora do intervalo permitido "
                      "(0 – 20).").format(row.grade, row.student, row.subject),
                    title=_("Nota fora do intervalo"),
                )

    def _validate_subjects_assigned(self):
        if not self.class_group or not self.academic_year:
            return
        assigned = set(
            frappe.get_all(
                "Class Subject Assignment",
                filters={
                    "class_group": self.class_group,
                    "academic_year": self.academic_year,
                    "is_active": 1,
                },
                pluck="subject",
            )
        )
        if not assigned:
            return  # skip if no assignments exist yet (allow saving during setup)
        for row in self.grade_rows:
            if row.subject and row.subject not in assigned:
                frappe.throw(
                    _("A disciplina <b>{0}</b> não tem uma Atribuição de "
                      "Disciplina activa para a Turma <b>{1}</b>. "
                      "Crie a atribuição antes de lançar notas.").format(
                        row.subject, self.class_group
                    ),
                    title=_("Disciplina não atribuída"),
                )
