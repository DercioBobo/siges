import frappe
from frappe import _
from frappe.model.document import Document


@frappe.whitelist()
def generate_promotion(doc_name):
    """
    Derive promotion decisions from the Annual Assessment for a class group.

    Decision rules:
    - 0 failed subjects + final class → Concluído
    - 0 failed subjects + non-final class → Promovido
    - ≥1 failed subjects → Retido

    A "final class" is one with no higher class_level in the same education_level.
    """
    doc = frappe.get_doc("Student Promotion", doc_name)

    # Locate the Annual Assessment for this turma + year
    ann_name = frappe.db.get_value(
        "Annual Assessment",
        {
            "academic_year": doc.academic_year,
            "class_group": doc.class_group,
        },
        "name",
    )
    if not ann_name:
        return {"error": "no_annual_assessment"}

    rows = frappe.get_all(
        "Annual Assessment Row",
        filters={"parent": ann_name},
        fields=["student", "result"],
    )
    if not rows:
        return {"error": "no_rows"}

    # Count failed subjects per student
    student_failed: dict = {}
    for row in rows:
        student_failed.setdefault(row.student, 0)
        if row.result == "Reprovado":
            student_failed[row.student] += 1

    is_final = _is_final_class(doc.school_class)

    result_rows = []
    for student in sorted(student_failed):
        failed_count = student_failed[student]
        if failed_count == 0 and is_final:
            decision = "Concluído"
        elif failed_count == 0:
            decision = "Promovido"
        else:
            decision = "Retido"

        result_rows.append(
            {
                "student": student,
                "total_failed_subjects": failed_count,
                "decision": decision,
                "remarks": "",
            }
        )

    return result_rows


def _is_final_class(school_class_name):
    """Return True when no higher class_level exists within the same education_level."""
    sc = frappe.db.get_value(
        "School Class",
        school_class_name,
        ["class_level", "education_level"],
        as_dict=True,
    )
    if not sc:
        return False
    higher = frappe.db.exists(
        "School Class",
        {
            "education_level": sc.education_level,
            "class_level": (">", sc.class_level),
            "is_active": 1,
        },
    )
    return not higher


class StudentPromotion(Document):
    def validate(self):
        self._validate_class_group_compatibility()
        self._validate_uniqueness()
        self._validate_annual_assessment_exists()

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
            "Student Promotion",
            {
                "academic_year": self.academic_year,
                "class_group": self.class_group,
                "name": ("!=", self.name),
            },
            "name",
        )
        if existing:
            frappe.throw(
                _("Já existe uma Promoção de Alunos para a Turma <b>{0}</b> "
                  "no Ano Lectivo <b>{1}</b>: <b>{2}</b>.").format(
                    self.class_group, self.academic_year, existing
                ),
                title=_("Promoção duplicada"),
            )

    def _validate_annual_assessment_exists(self):
        if not (self.academic_year and self.class_group):
            return
        ann = frappe.db.get_value(
            "Annual Assessment",
            {
                "academic_year": self.academic_year,
                "class_group": self.class_group,
            },
            "name",
        )
        if not ann:
            frappe.throw(
                _("Não existe uma Avaliação Anual para a Turma <b>{0}</b> "
                  "no Ano Lectivo <b>{1}</b>. Crie e calcule a Avaliação Anual "
                  "antes de gerar a Promoção.").format(
                    self.class_group, self.academic_year
                ),
                title=_("Avaliação Anual em falta"),
            )
