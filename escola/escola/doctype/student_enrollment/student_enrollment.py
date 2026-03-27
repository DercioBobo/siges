import frappe
from frappe import _
from frappe.model.document import Document


class StudentEnrollment(Document):
    def before_insert(self):
        self._fetch_student_defaults()

    def validate(self):
        self._validate_duplicate_active_enrollment()

    def _fetch_student_defaults(self):
        """Pull guardian and enrollment type from the Student record when creating."""
        if not self.student:
            return
        student = frappe.db.get_value(
            "Student",
            self.student,
            ["primary_guardian", "enrollment_type"],
            as_dict=True,
        )
        if not student:
            return
        if not self.primary_guardian and student.primary_guardian:
            self.primary_guardian = student.primary_guardian
        if not self.enrollment_type and student.enrollment_type:
            self.enrollment_type = student.enrollment_type

    def _validate_duplicate_active_enrollment(self):
        if self.enrollment_status != "Activa":
            return
        existing = frappe.db.get_value(
            "Student Enrollment",
            {
                "student": self.student,
                "academic_year": self.academic_year,
                "enrollment_status": "Activa",
                "name": ("!=", self.name),
            },
            "name",
        )
        if existing:
            frappe.throw(
                _("O aluno já possui uma inscrição activa para o Ano Lectivo <b>{0}</b>: "
                  "<b>{1}</b>. Cancele ou conclua a inscrição existente antes de criar "
                  "uma nova.").format(self.academic_year, existing),
                title=_("Inscrição duplicada"),
            )
