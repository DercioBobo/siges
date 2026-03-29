import json

import frappe
from frappe import _
from frappe.model.document import Document
from escola.escola.doctype.class_curriculum.class_curriculum import get_curriculum_subjects


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

    subject_lines = get_curriculum_subjects(class_group)

    if not student_assignments:
        return {"error": "no_students"}
    if not subject_lines:
        return {"error": "no_subjects"}

    rows = []
    for sa in student_assignments:
        for sl in subject_lines:
            rows.append(
                {
                    "student": sa.student,
                    "subject": sl.subject,
                    "teacher": sl.teacher or None,
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
        self._validate_components()
        self._validate_score_ranges()
        self._calculate_row_averages()
        self._calculate_class_summary()
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
    # Component validations
    # ------------------------------------------------------------------

    def _validate_components(self):
        if not self.evaluation_components:
            return
        total_weight = sum(c.weight or 0 for c in self.evaluation_components)
        if total_weight and abs(total_weight - 100) > 0.01:
            frappe.msgprint(
                _("A soma dos pesos das componentes é <b>{0}%</b>. "
                  "Recomenda-se que a soma seja exactamente 100%.").format(
                    round(total_weight, 2)
                ),
                indicator="orange",
                alert=True,
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

    def _validate_score_ranges(self):
        """Validate each component score is within 0 – max_score."""
        if not self.evaluation_components:
            return
        max_scores = {c.component_name: (c.max_score or 20) for c in self.evaluation_components}
        for row in self.grade_rows:
            if not row.scores_json:
                continue
            try:
                scores = json.loads(row.scores_json)
            except (ValueError, TypeError):
                continue
            for comp_name, score in scores.items():
                if score is None:
                    continue
                max_s = max_scores.get(comp_name, 20)
                if score < 0 or score > max_s:
                    frappe.throw(
                        _("A nota <b>{0}</b> na componente <b>{1}</b> "
                          "do aluno <b>{2}</b> / disciplina <b>{3}</b> "
                          "está fora do intervalo permitido "
                          "(0 – {4}).").format(
                            score, comp_name, row.student, row.subject, max_s
                        ),
                        title=_("Nota fora do intervalo"),
                    )

    # ------------------------------------------------------------------
    # Calculations
    # ------------------------------------------------------------------

    def _calculate_row_averages(self):
        """Compute weighted trimester_average from scores_json + evaluation_components."""
        if not self.evaluation_components:
            # No components defined — clear derived fields
            for row in self.grade_rows:
                row.trimester_average = None
                row.is_approved = 0
            return

        total_weight = sum(c.weight or 0 for c in self.evaluation_components)
        components = {c.component_name: c for c in self.evaluation_components}

        for row in self.grade_rows:
            if row.is_absent:
                row.trimester_average = 0.0
                row.is_approved = 0
                continue

            if not row.scores_json:
                row.trimester_average = None
                row.is_approved = 0
                continue

            try:
                scores = json.loads(row.scores_json)
            except (ValueError, TypeError):
                row.trimester_average = None
                row.is_approved = 0
                continue

            weighted_sum = 0.0
            used_weight = 0.0
            for comp_name, comp in components.items():
                score = scores.get(comp_name)
                if score is None:
                    continue
                max_s = comp.max_score or 20
                # Normalise to 0-20 scale then apply weight
                normalised = (score / max_s) * 20 if max_s else 0
                weighted_sum += normalised * (comp.weight or 0)
                used_weight += comp.weight or 0

            if used_weight > 0:
                avg = round(weighted_sum / used_weight, 2) if total_weight else 0
                row.trimester_average = avg
                row.is_approved = 1 if avg >= 10 else 0
            else:
                row.trimester_average = None
                row.is_approved = 0

    def _calculate_class_summary(self):
        averages = [
            row.trimester_average
            for row in self.grade_rows
            if row.trimester_average is not None and not row.is_absent
        ]
        if averages:
            self.class_average = round(sum(averages) / len(averages), 2)
        else:
            self.class_average = 0

        self.total_approved = sum(1 for row in self.grade_rows if row.is_approved)
        self.total_failed = sum(
            1 for row in self.grade_rows
            if not row.is_approved and not row.is_absent and row.trimester_average is not None
        )

    def _validate_subjects_assigned(self):
        if not self.class_group:
            return
        curriculum_subjects = get_curriculum_subjects(self.class_group)
        assigned = {sl.subject for sl in curriculum_subjects}
        if not assigned:
            return  # skip if no curriculum exists yet (allow saving during setup)
        for row in self.grade_rows:
            if row.subject and row.subject not in assigned:
                frappe.throw(
                    _("A disciplina <b>{0}</b> não consta da Grelha Curricular activa "
                      "para a Classe <b>{1}</b>. "
                      "Adicione a disciplina à Grelha Curricular antes de lançar notas.").format(
                        row.subject, self.school_class
                    ),
                    title=_("Disciplina não atribuída"),
                )
