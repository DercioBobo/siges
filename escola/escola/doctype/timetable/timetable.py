import frappe
from frappe import _
from frappe.model.document import Document


class Timetable(Document):
    def validate(self):
        self._validate_uniqueness()
        self._validate_teacher_conflicts()
        self._auto_archive_previous()

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    def _validate_uniqueness(self):
        """Warn when another Active timetable already exists for same turma + period."""
        if self.status != "Activo":
            return
        existing = frappe.db.get_value(
            "Timetable",
            {
                "class_group":    self.class_group,
                "academic_year":  self.academic_year,
                "status":         "Activo",
                "name":           ("!=", self.name or ""),
            },
            "name",
        )
        if existing:
            frappe.msgprint(
                _("O horário <b>{0}</b> já está Activo para esta turma e período — "
                  "será arquivado automaticamente ao guardar.").format(existing),
                title=_("Horário anterior encontrado"),
                indicator="orange",
            )

    def _validate_teacher_conflicts(self):
        """Warn when a teacher is assigned to two different turmas at the same day/slot."""
        if not self.timetable_entries:
            return

        # Only check Aula-type slots; interval rows have no teacher
        aula_slots = {
            ts.name
            for ts in frappe.get_all(
                "Time Slot", filters={"slot_type": "Aula"}, fields=["name"]
            )
        }

        conflicts = []
        for entry in self.timetable_entries:
            if not entry.teacher or not entry.time_slot:
                continue
            if entry.time_slot not in aula_slots:
                continue

            clash = frappe.db.sql(
                """
                SELECT te.parent
                FROM   `tabTimetable Entry` te
                JOIN   `tabTimetable` t ON t.name = te.parent
                WHERE  te.teacher    = %s
                  AND  te.day_of_week = %s
                  AND  te.time_slot   = %s
                  AND  t.status       = 'Activo'
                  AND  te.parent     != %s
                LIMIT 1
                """,
                (entry.teacher, entry.day_of_week, entry.time_slot, self.name or ""),
            )
            if clash:
                teacher_name = frappe.db.get_value("Teacher", entry.teacher, "full_name") or entry.teacher
                conflicts.append(f"{teacher_name} — {entry.day_of_week} / {entry.time_slot}")

        if conflicts:
            frappe.msgprint(
                _("Atenção: conflitos de horário detectados para os seguintes professores:"
                  "<br><br>{0}").format("<br>".join(conflicts)),
                title=_("Conflitos de Horário"),
                indicator="orange",
            )

    def _auto_archive_previous(self):
        """When this timetable is set to Active, archive any previous active one."""
        if self.status != "Activo":
            return
        previous = frappe.get_all(
            "Timetable",
            filters={
                "class_group":   self.class_group,
                "academic_year": self.academic_year,
                "status":        "Activo",
                "name":          ("!=", self.name or ""),
            },
            fields=["name"],
        )
        for prev in previous:
            frappe.db.set_value("Timetable", prev.name, "status", "Arquivado")


# ---------------------------------------------------------------------------
# Whitelisted helpers called from the form JS
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_curriculum_teacher(class_group, subject):
    """
    Return the teacher assigned to *subject* for *class_group*.

    Resolution order:
    1. Class Group Subject Line (new path — secondary schools)
    2. Primary fallback: class_teacher for non-specialist subjects (Professor Único)
    3. Legacy fallback: active Class Curriculum (existing data)
    """
    school_class = frappe.db.get_value("Class Group", class_group, "school_class")

    # 1. Per-turma override: explicit row on the Class Group itself
    teacher = frappe.db.get_value(
        "Class Group Subject Line",
        {"parent": class_group, "subject": subject},
        "teacher",
    )
    if teacher:
        return teacher

    # 2. Class-wide default: School Class subjects table
    if school_class:
        teacher = frappe.db.get_value(
            "School Class Subject",
            {"parent": school_class, "subject": subject},
            "teacher",
        )
        if teacher:
            return teacher

    # 3. Professor Único → class_teacher for non-specialist subjects
    teaching_model = (
        frappe.db.get_value("School Class", school_class, "teaching_model")
        if school_class else None
    )
    if teaching_model == "Professor Único":
        is_specialist = frappe.db.get_value("Subject", subject, "is_specialist")
        if not is_specialist:
            return frappe.db.get_value("Class Group", class_group, "class_teacher")
        return None

    # 4. Legacy fallback: active Class Curriculum (for groups not yet migrated)
    curriculum = frappe.db.get_value(
        "Class Curriculum",
        {"class_group": class_group, "is_active": 1},
        "name",
    )
    if not curriculum:
        return None

    teacher = frappe.db.get_value(
        "Class Curriculum Line",
        {"parent": curriculum, "subject": subject},
        "teacher",
    )
    if teacher:
        return teacher

    is_specialist = frappe.db.get_value("Subject", subject, "is_specialist")
    if not is_specialist:
        return frappe.db.get_value("Class Group", class_group, "class_teacher")

    return None
