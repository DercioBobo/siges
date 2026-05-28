import frappe
from frappe.model.document import Document


@frappe.whitelist()
def get_turmas_summary(school_class):
    """Return class groups linked to school_class with teacher name and student count."""
    return frappe.db.sql(
        """
        SELECT
            cg.name,
            cg.academic_year,
            cg.is_active,
            COALESCE(t.full_name, '') AS teacher_name,
            COUNT(cgs.name)           AS student_count
        FROM      `tabClass Group`         cg
        LEFT JOIN `tabTeacher`             t   ON t.name  = cg.class_teacher
        LEFT JOIN `tabClass Group Student` cgs ON cgs.parent = cg.name
        WHERE cg.school_class = %(school_class)s
        GROUP BY cg.name, cg.academic_year, cg.is_active, t.full_name
        ORDER BY cg.academic_year DESC, cg.name ASC
        """,
        {"school_class": school_class},
        as_dict=True,
    )


class SchoolClass(Document):
    def validate(self):
        self._sort_subjects_by_order()
        self._enforce_teaching_model()
        if self.class_level is not None and self.class_level < 0:
            frappe.throw(
                frappe._("O Nível da Classe não pode ser negativo."),
                title=frappe._("Nível inválido"),
            )

    def _enforce_teaching_model(self):
        """teaching_model is strictly determined by education_level — cannot be overridden."""
        if self.education_level == "Primário":
            self.teaching_model = "Professor Único"
        elif self.education_level == "Secundário":
            self.teaching_model = "Professores por Disciplina"

    def _sort_subjects_by_order(self):
        if not self.subjects:
            return
        self.subjects.sort(key=lambda r: (r.sort_order if r.sort_order is not None else 999, r.idx or 0))
        for i, row in enumerate(self.subjects):
            row.idx = i + 1
