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
        """Only one active Class Curriculum per class_group."""
        if not self.is_active or not self.class_group:
            return
        existing = frappe.db.get_value(
            "Class Curriculum",
            {"class_group": self.class_group, "is_active": 1, "name": ("!=", self.name)},
            "name",
        )
        if existing:
            frappe.throw(
                _("Já existe uma Grelha Curricular activa para a Turma <b>{0}</b>: <b>{1}</b>. "
                  "Desactive a grelha anterior antes de criar uma nova.").format(
                    self.class_group, existing
                ),
                title=_("Grelha duplicada"),
            )


def get_curriculum_subjects(class_group):
    """
    Return the subject lines for the active curriculum of a class group.
    Returns list of dicts: {subject, teacher}.
    """
    curriculum_name = frappe.db.get_value(
        "Class Curriculum",
        {"class_group": class_group, "is_active": 1},
        "name",
    )
    if not curriculum_name:
        return []

    return frappe.get_all(
        "Class Curriculum Line",
        filters={"parent": curriculum_name},
        fields=["subject", "teacher"],
        order_by="idx asc",
    )


@frappe.whitelist()
def get_class_group_curriculum_data(class_group):
    """
    Return everything needed to auto-populate a curriculum when a class_group is selected:
    - class_teacher from the Class Group
    - subjects from the School Class (with is_specialist flag)
    Called client-side on class_group change.
    """
    cg = frappe.db.get_value(
        "Class Group", class_group, ["school_class", "class_teacher"], as_dict=True
    )
    if not cg:
        return {"error": "class_group_not_found"}

    subject_rows = frappe.get_all(
        "School Class Subject",
        filters={"parent": cg.school_class},
        fields=["subject"],
        order_by="idx asc",
    )
    if not subject_rows:
        return {"error": "no_subjects", "school_class": cg.school_class}

    subject_names = [r.subject for r in subject_rows]
    specialist_records = frappe.get_all(
        "Subject",
        filters=[["name", "in", subject_names]],
        fields=["name", "is_specialist"],
    )
    specialist_set = {r.name for r in specialist_records if r.is_specialist}

    return {
        "class_teacher": cg.class_teacher,
        "school_class": cg.school_class,
        "subjects": [
            {"subject": r.subject, "is_specialist": r.subject in specialist_set}
            for r in subject_rows
        ],
    }
