import frappe
from frappe import _
from frappe.model.document import Document


@frappe.whitelist()
def get_attendance_students(class_group, academic_year):
    """Return active students for the class group — used to pre-fill the attendance table."""
    return frappe.get_all(
        "Student Group Assignment",
        filters={
            "class_group": class_group,
            "academic_year": academic_year,
            "status": "Activa",
        },
        fields=["student"],
        order_by="student asc",
    )


def get_annual_absences(class_group, academic_year):
    """Return total absences per student for the full year.

    Used by Annual Assessment to display faltas alongside grades.
    Returns dict: {student: {"justified": N, "unjustified": N, "total": N}}
    """
    records = frappe.get_all(
        "Term Attendance",
        filters={
            "class_group": class_group,
            "academic_year": academic_year,
            "docstatus": ("!=", 2),
        },
        fields=["name"],
    )

    result = {}
    for rec in records:
        rows = frappe.get_all(
            "Term Attendance Row",
            filters={"parent": rec.name},
            fields=["student", "justified_absences", "unjustified_absences", "total_absences"],
        )
        for row in rows:
            entry = result.setdefault(row.student, {"justified": 0, "unjustified": 0, "total": 0})
            entry["justified"] += row.justified_absences or 0
            entry["unjustified"] += row.unjustified_absences or 0
            entry["total"] += row.total_absences or 0

    return result


class TermAttendance(Document):
    def validate(self):
        self._validate_uniqueness()
        self._calculate_totals()

    def _validate_uniqueness(self):
        existing = frappe.db.get_value(
            "Term Attendance",
            {
                "class_group": self.class_group,
                "academic_term": self.academic_term,
                "name": ("!=", self.name),
            },
            "name",
        )
        if existing:
            frappe.throw(
                _("Já existe um Resumo de Faltas para a Turma <b>{0}</b> "
                  "no Período <b>{1}</b>: <b>{2}</b>.").format(
                    self.class_group, self.academic_term, existing
                ),
                title=_("Registo duplicado"),
            )

    def _calculate_totals(self):
        threshold = int(
            frappe.db.get_single_value("School Settings", "max_absences_threshold") or 0
        )
        at_risk_count = 0
        for row in self.attendance_rows:
            row.total_absences = (row.justified_absences or 0) + (row.unjustified_absences or 0)
            row.at_risk = 1 if (threshold > 0 and row.total_absences >= threshold) else 0
            if row.at_risk:
                at_risk_count += 1
        self.total_students = len(self.attendance_rows)
        self.students_at_risk = at_risk_count


@frappe.whitelist()
def sync_term_attendance_students(doc_name):
    """Remove rows for students whose current_status is not 'Activo'. Preserves absences."""
    doc = frappe.get_doc("Term Attendance", doc_name)
    if not doc.attendance_rows:
        return {"removed": 0, "kept": 0}

    students = [row.student for row in doc.attendance_rows]
    active = set(
        frappe.get_all(
            "Student",
            filters={"name": ("in", students), "current_status": "Activo"},
            pluck="name",
        )
    )

    original = len(doc.attendance_rows)
    kept = [r for r in doc.attendance_rows if r.student in active]
    removed = original - len(kept)

    if removed:
        doc.set("attendance_rows", kept)
        doc.save(ignore_permissions=True)

    return {"removed": removed, "kept": len(kept)}
