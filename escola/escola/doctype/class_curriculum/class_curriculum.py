import frappe
from frappe import _
from frappe.model.document import Document


class ClassCurriculum(Document):
    def validate(self):
        self._validate_has_lines()
        self._validate_no_duplicate_subjects()
        self._validate_teachers_active()
        self._validate_uniqueness()

    def _validate_has_lines(self):
        if not self.subject_lines:
            frappe.throw(_("A Grelha Curricular deve ter pelo menos uma disciplina."))

    def _validate_no_duplicate_subjects(self):
        seen = set()
        for line in self.subject_lines:
            if line.subject in seen:
                frappe.throw(
                    _("A disciplina <b>{0}</b> está duplicada na grelha.").format(line.subject),
                    title=_("Disciplina duplicada"),
                )
            seen.add(line.subject)

    def _validate_teachers_active(self):
        for line in self.subject_lines:
            if not line.teacher:
                continue
            is_active = frappe.db.get_value("Teacher", line.teacher, "is_active")
            if not is_active:
                frappe.throw(
                    _("O professor <b>{0}</b> atribuído à disciplina <b>{1}</b> não está activo.").format(
                        line.teacher, line.subject
                    ),
                    title=_("Professor inactivo"),
                )

    def _validate_uniqueness(self):
        """Only one active Class Curriculum per school_class (+ academic_year if set)."""
        if not self.is_active or not self.school_class:
            return

        filters = {
            "school_class": self.school_class,
            "is_active": 1,
            "name": ("!=", self.name),
        }
        if self.academic_year:
            filters["academic_year"] = self.academic_year

        existing = frappe.db.get_value("Class Curriculum", filters, "name")
        if existing:
            year_label = f" / {self.academic_year}" if self.academic_year else ""
            frappe.throw(
                _("Já existe uma Grelha Curricular activa para a Classe <b>{0}{1}</b>: <b>{2}</b>. "
                  "Desactive a grelha anterior antes de criar uma nova.").format(
                    self.school_class, year_label, existing
                ),
                title=_("Grelha duplicada"),
            )


def get_curriculum_subjects(school_class, academic_year=None):
    """
    Return the subject lines for the active curriculum of a class.
    Prefers year-specific match; falls back to a curriculum with no academic_year.
    Returns list of dicts: {subject, teacher}.
    """
    curriculum_name = _find_curriculum(school_class, academic_year)
    if not curriculum_name:
        return []

    return frappe.get_all(
        "Class Curriculum Line",
        filters={"parent": curriculum_name},
        fields=["subject", "teacher"],
        order_by="idx asc",
    )


def _find_curriculum(school_class, academic_year=None):
    """Find the active Class Curriculum for a class, with year-specific priority."""
    if academic_year:
        name = frappe.db.get_value(
            "Class Curriculum",
            {"school_class": school_class, "academic_year": academic_year, "is_active": 1},
            "name",
        )
        if name:
            return name

    return frappe.db.get_value(
        "Class Curriculum",
        {"school_class": school_class, "is_active": 1},
        "name",
        order_by="creation desc",
    )
