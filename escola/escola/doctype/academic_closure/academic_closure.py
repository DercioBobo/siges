import frappe
from frappe import _
from frappe.model.document import Document


class AcademicClosure(Document):
    def validate(self):
        self._validate_uniqueness()
        self._validate_no_duplicate_students()
        self._validate_average_ranges()
        self._recalculate_summary()

    def _validate_uniqueness(self):
        existing = frappe.db.get_value(
            "Academic Closure",
            {
                "class_group": self.class_group,
                "academic_year": self.academic_year,
                "name": ("!=", self.name),
            },
            "name",
        )
        if existing:
            frappe.throw(
                _("Já existe um Fecho Académico ({0}) para a turma {1} no ano lectivo {2}.").format(
                    existing, self.class_group, self.academic_year
                )
            )

    def _validate_no_duplicate_students(self):
        seen = set()
        for row in self.closure_rows:
            if row.student in seen:
                frappe.throw(
                    _("O aluno {0} está duplicado no Fecho Académico.").format(row.student)
                )
            seen.add(row.student)

    def _validate_average_ranges(self):
        for row in self.closure_rows:
            if row.overall_average and (row.overall_average < 0 or row.overall_average > 20):
                frappe.throw(
                    _("A média do aluno {0} deve estar entre 0 e 20. Valor: {1}.").format(
                        row.student, row.overall_average
                    )
                )

    def _recalculate_summary(self):
        rows = self.closure_rows or []
        self.total_students = len(rows)
        self.promoted_students = sum(1 for r in rows if r.final_decision == "Promovido")
        self.retained_students = sum(1 for r in rows if r.final_decision == "Retido")
        self.concluded_students = sum(1 for r in rows if r.final_decision == "Concluído")


@frappe.whitelist()
def load_promotions(doc_name):
    """
    Fetch Student Promotion rows for the class_group + academic_year on
    this Academic Closure. Also tries to pull per-student averages from
    Annual Assessment if available.
    """
    doc = frappe.get_doc("Academic Closure", doc_name)

    if not doc.class_group or not doc.academic_year:
        frappe.throw(_("Preencha o Ano Lectivo e a Turma antes de carregar as promoções."))

    promotion = frappe.db.get_value(
        "Student Promotion",
        {
            "class_group": doc.class_group,
            "academic_year": doc.academic_year,
        },
        "name",
    )
    if not promotion:
        return {"error": "no_promotion"}

    promo_rows = frappe.get_all(
        "Student Promotion Row",
        filters={"parent": promotion},
        fields=["student", "decision", "total_failed_subjects", "remarks"],
        order_by="student asc",
    )
    if not promo_rows:
        return {"error": "no_rows"}

    # Build per-student average map from Annual Assessment rows
    avg_map = {}
    annual = frappe.db.get_value(
        "Annual Assessment",
        {
            "class_group": doc.class_group,
            "academic_year": doc.academic_year,
        },
        "name",
    )
    if annual:
        ann_rows = frappe.get_all(
            "Annual Assessment Row",
            filters={"parent": annual},
            fields=["student", "final_grade"],
        )
        by_student = {}
        for r in ann_rows:
            by_student.setdefault(r.student, []).append(r.final_grade)
        for student, grades in by_student.items():
            avg_map[student] = round(sum(grades) / len(grades), 1) if grades else 0

    result_rows = [
        {
            "student": r.student,
            "final_decision": r.decision,
            "total_failed_subjects": r.total_failed_subjects or 0,
            "overall_average": avg_map.get(r.student, 0),
            "remarks": r.remarks or "",
        }
        for r in promo_rows
    ]

    return {"rows": result_rows}


@frappe.whitelist()
def create_report_cards(doc_name):
    """
    Create one Report Card document per student in the closure_rows,
    skipping students who already have a Report Card for this academic_year.
    Returns lists of created and skipped names.
    """
    doc = frappe.get_doc("Academic Closure", doc_name)

    if not doc.closure_rows:
        return {"error": "no_closure_rows"}

    annual = frappe.db.get_value(
        "Annual Assessment",
        {
            "class_group": doc.class_group,
            "academic_year": doc.academic_year,
        },
        "name",
    )

    created = []
    skipped = []

    for row in doc.closure_rows:
        existing = frappe.db.get_value(
            "Report Card",
            {
                "student": row.student,
                "academic_year": doc.academic_year,
            },
            "name",
        )
        if existing:
            skipped.append(row.student)
            continue

        assessment_rows = []
        if annual:
            assessment_rows = frappe.get_all(
                "Annual Assessment Row",
                filters={"parent": annual, "student": row.student},
                fields=["subject", "final_grade", "result", "remarks"],
                order_by="subject asc",
            )

        primary_guardian = frappe.db.get_value("Student", row.student, "primary_guardian")

        rc = frappe.new_doc("Report Card")
        rc.student = row.student
        rc.academic_year = doc.academic_year
        rc.school_class = doc.school_class
        rc.class_group = doc.class_group
        rc.primary_guardian = primary_guardian
        rc.final_decision = row.final_decision

        for ar in assessment_rows:
            rc.append(
                "report_card_rows",
                {
                    "subject": ar.subject,
                    "final_grade": ar.final_grade,
                    "result": ar.result,
                    "remarks": ar.remarks or "",
                },
            )

        rc.insert(ignore_permissions=False)
        created.append(rc.name)

    return {"created": created, "skipped": skipped}
