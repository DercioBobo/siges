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
        self._auto_fill_subject_teachers()
        if self.class_level is not None and self.class_level < 0:
            frappe.throw(
                frappe._("O Nível da Classe não pode ser negativo."),
                title=frappe._("Nível inválido"),
            )
        if self.minimum_passing_grade is not None and self.minimum_passing_grade < 0:
            frappe.throw(
                frappe._("A Nota Mínima de Aprovação não pode ser negativa."),
                title=frappe._("Nota inválida"),
            )
        if self.default_teacher:
            is_active = frappe.db.get_value("Teacher", self.default_teacher, "is_active")
            if not is_active:
                frappe.throw(
                    frappe._("O professor <b>{0}</b> não está activo.").format(
                        self.default_teacher
                    ),
                    title=frappe._("Professor inactivo"),
                )

    def _auto_fill_subject_teachers(self):
        """Professor Único: fill blank non-specialist subject rows with default_teacher."""
        if self.teaching_model != "Professor Único" or not self.default_teacher:
            return
        if not self.subjects:
            return
        specialist_subjects = set(frappe.get_all(
            "Subject", filters={"is_specialist": 1}, pluck="name"
        ))
        for row in self.subjects:
            if not row.subject or row.teacher or row.subject in specialist_subjects:
                continue
            row.teacher = self.default_teacher

    def _sort_subjects_by_order(self):
        if not self.subjects:
            return
        self.subjects.sort(key=lambda r: (r.sort_order if r.sort_order is not None else 999, r.idx or 0))
        for i, row in enumerate(self.subjects):
            row.idx = i + 1
