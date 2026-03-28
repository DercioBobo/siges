import frappe
from frappe import _
from frappe.model.document import Document


class ClassGroup(Document):
    def validate(self):
        self._validate_class_teacher()
        if self.max_students is not None and self.max_students < 1:
            frappe.throw(
                _("A Capacidade Máxima deve ser um número positivo."),
                title=_("Capacidade inválida"),
            )

    def _validate_class_teacher(self):
        if not self.class_teacher:
            return
        is_active = frappe.db.get_value("Teacher", self.class_teacher, "is_active")
        if not is_active:
            frappe.throw(
                _("O professor <b>{0}</b> não está activo e não pode ser designado "
                  "como Professor Titular.").format(self.class_teacher),
                title=_("Professor inactivo"),
            )


@frappe.whitelist()
def add_students_to_group(class_group_name, students):
    """
    Bulk-create Student Group Assignments for a list of students.
    `students` is a JSON-encoded list of student names.
    """
    import json
    if isinstance(students, str):
        students = json.loads(students)

    cg_data = frappe.db.get_value(
        "Class Group", class_group_name,
        ["academic_year", "school_class"], as_dict=True
    )
    today = frappe.utils.today()
    created, skipped, errors = [], [], []

    for student in students:
        if frappe.db.exists("Student Group Assignment", {
            "student": student,
            "class_group": class_group_name,
            "status": "Activa",
        }):
            skipped.append(student)
            continue
        try:
            frappe.get_doc({
                "doctype": "Student Group Assignment",
                "student": student,
                "class_group": class_group_name,
                "academic_year": cg_data.academic_year,
                "school_class": cg_data.school_class,
                "assignment_date": today,
                "status": "Activa",
            }).insert()
            created.append(student)
        except frappe.ValidationError as e:
            errors.append({"student": student, "error": str(e)})

    frappe.db.commit()
    return {"created": len(created), "skipped": len(skipped), "errors": errors}


@frappe.whitelist()
def remove_student_from_group(class_group_name, student):
    """
    Mark a student's active SGA as Encerrada, which triggers the roster sync hook.
    """
    sga_name = frappe.db.get_value(
        "Student Group Assignment",
        {"student": student, "class_group": class_group_name, "status": "Activa"},
        "name",
    )
    if not sga_name:
        frappe.throw(
            _("Não foi encontrada uma alocação activa para este aluno nesta turma."),
            title=_("Alocação não encontrada"),
        )
    sga = frappe.get_doc("Student Group Assignment", sga_name)
    sga.status = "Encerrada"
    sga.save()
    frappe.db.commit()
    return sga_name


@frappe.whitelist()
def rebuild_roster(class_group_name):
    """
    Rebuild the student roster from active Student Group Assignments.
    Safe to call at any time — idempotent.
    """
    frappe.db.delete("Class Group Student", {"parent": class_group_name})

    assignments = frappe.get_all(
        "Student Group Assignment",
        filters={"class_group": class_group_name, "status": "Activa"},
        fields=["name", "student"],
        order_by="student asc",
    )

    for idx, sga in enumerate(assignments, start=1):
        frappe.get_doc({
            "doctype": "Class Group Student",
            "parent": class_group_name,
            "parentfield": "students",
            "parenttype": "Class Group",
            "idx": idx,
            "student": sga.student,
            "assignment": sga.name,
        }).insert(ignore_permissions=True)

    count = len(assignments)
    frappe.db.set_value(
        "Class Group", class_group_name, "student_count", count, update_modified=False
    )
    frappe.db.commit()
    return count


def sync_student_in_rosters(doc, method=None):
    """
    Called via doc_events when a Student record is saved.
    Updates student_name in every Class Group Student row for this student.
    """
    if not doc.full_name:
        return
    frappe.db.sql(
        """UPDATE `tabClass Group Student`
           SET student_name = %s
           WHERE student = %s""",
        (doc.full_name, doc.name),
    )
