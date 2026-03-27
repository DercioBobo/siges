import frappe
from frappe import _
from frappe.model.document import Document


@frappe.whitelist()
def get_students_for_attendance(class_group, academic_year):
    """Return the list of active students for a class group and academic year.

    Called from the client-side "Carregar Alunos" button.
    """
    assignments = frappe.get_all(
        "Student Group Assignment",
        filters={
            "class_group": class_group,
            "academic_year": academic_year,
            "status": "Activa",
        },
        fields=["student"],
        order_by="student asc",
    )
    if not assignments:
        return []

    student_names = [a.student for a in assignments]
    students = frappe.get_all(
        "Student",
        filters={"name": ("in", student_names)},
        fields=["name", "full_name"],
    )
    # Preserve sort order from assignments
    student_map = {s.name: s.full_name for s in students}
    return [
        {"student": a.student, "full_name": student_map.get(a.student, a.student)}
        for a in assignments
    ]


class StudentAttendance(Document):
    def validate(self):
        self._validate_class_group_compatibility()
        self._validate_uniqueness()
        self._validate_entries_not_empty()
        self._validate_no_duplicate_students()

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
        if not cg.is_active:
            frappe.throw(
                _("A Turma <b>{0}</b> não está activa.").format(self.class_group),
                title=_("Turma inactiva"),
            )

    def _validate_uniqueness(self):
        existing = frappe.db.get_value(
            "Student Attendance",
            {
                "attendance_date": self.attendance_date,
                "class_group": self.class_group,
                "name": ("!=", self.name),
            },
            "name",
        )
        if existing:
            frappe.throw(
                _("Já existe uma lista de presença para a Turma <b>{0}</b> "
                  "na data <b>{1}</b>: <b>{2}</b>.").format(
                    self.class_group,
                    frappe.format(self.attendance_date, {"fieldtype": "Date"}),
                    existing,
                ),
                title=_("Presença duplicada"),
            )

    def _validate_entries_not_empty(self):
        if not self.attendance_entries:
            frappe.throw(
                _("A Lista de Presença não pode estar vazia. "
                  "Utilize o botão <b>Carregar Alunos</b> para preencher a lista."),
                title=_("Lista vazia"),
            )

    def _validate_no_duplicate_students(self):
        seen = set()
        for row in self.attendance_entries:
            if row.student in seen:
                frappe.throw(
                    _("O aluno <b>{0}</b> aparece mais de uma vez na "
                      "Lista de Presença.").format(row.student),
                    title=_("Aluno duplicado"),
                )
            seen.add(row.student)
