import frappe
from frappe import _
from frappe.model.document import Document


class StudentGroupAssignment(Document):
    def validate(self):
        self._validate_class_group_belongs()
        self._validate_duplicate_active_assignment()
        self._validate_class_group_capacity()

    def after_insert(self):
        _roster_sync(self)

    def on_update(self):
        _roster_sync(self)

    def on_trash(self):
        _roster_remove(self.name)
        _update_student_count(self.class_group)

    # ------------------------------------------------------------------

    def _validate_class_group_belongs(self):
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
        if not cg.is_active:
            frappe.throw(
                _("A Turma <b>{0}</b> não está activa.").format(self.class_group),
                title=_("Turma inactiva"),
            )

    def _validate_duplicate_active_assignment(self):
        if self.status != "Activa":
            return
        existing = frappe.db.get_value(
            "Student Group Assignment",
            {
                "student": self.student,
                "academic_year": self.academic_year,
                "status": "Activa",
                "name": ("!=", self.name),
            },
            "name",
        )
        if existing:
            frappe.throw(
                _("O aluno já possui uma alocação activa para o Ano Lectivo "
                  "<b>{0}</b>: <b>{1}</b>. Encerre ou transfira a alocação "
                  "existente antes de criar uma nova.").format(
                    self.academic_year, existing
                ),
                title=_("Alocação duplicada"),
            )

    def _validate_class_group_capacity(self):
        if not self.class_group or self.status != "Activa":
            return
        max_students = frappe.db.get_value(
            "Class Group", self.class_group, "max_students"
        )
        if not max_students:
            return
        active_count = frappe.db.count(
            "Student Group Assignment",
            {
                "class_group": self.class_group,
                "academic_year": self.academic_year,
                "status": "Activa",
                "name": ("!=", self.name),
            },
        )
        if active_count >= max_students:
            frappe.throw(
                _("A Turma <b>{0}</b> atingiu a capacidade máxima de "
                  "<b>{1}</b> alunos.").format(self.class_group, max_students),
                title=_("Capacidade esgotada"),
            )


# ------------------------------------------------------------------
# Roster sync helpers (called from lifecycle hooks and rebuild_roster)
# ------------------------------------------------------------------

def _roster_sync(sga):
    """Remove any existing roster row for this assignment, then re-add if still active."""
    # Find the class_group this row currently lives in (may differ from sga.class_group
    # if the assignment was just moved to a different group)
    old_parents = frappe.db.get_all(
        "Class Group Student",
        filters={"assignment": sga.name},
        fields=["name", "parent"],
        ignore_permissions=True,
    )

    affected_groups = {row.parent for row in old_parents}
    _roster_remove(sga.name)

    if sga.status == "Activa":
        frappe.get_doc({
            "doctype": "Class Group Student",
            "parent": sga.class_group,
            "parentfield": "students",
            "parenttype": "Class Group",
            "student": sga.student,
            "assignment": sga.name,
        }).insert(ignore_permissions=True)
        affected_groups.add(sga.class_group)

    for cg_name in affected_groups:
        _update_student_count(cg_name)


def _roster_remove(assignment_name):
    frappe.db.delete("Class Group Student", {"assignment": assignment_name})


def _update_student_count(class_group_name):
    if not class_group_name:
        return
    count = frappe.db.count("Class Group Student", {"parent": class_group_name})
    frappe.db.set_value(
        "Class Group", class_group_name, "student_count", count, update_modified=False
    )
