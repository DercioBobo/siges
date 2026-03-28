import frappe
from frappe import _
from frappe.model.document import Document


@frappe.whitelist()
def generate_promotion(doc_name):
    """
    Derive promotion decisions from the Annual Assessment for a class group.

    Decision rules (evaluated in order):
    - 0 failed subjects + final class  → Concluído
    - 0 failed subjects + non-final    → Promovido
    - avg ≥ 8.0 and avg < min_grade    → Recurso  (borderline — remedial exam)
    - otherwise                         → Retido

    A "failed" subject is one whose final_grade < school_class.minimum_passing_grade.
    A "final class" is one with no higher class_level in the same education_level.
    Manual overrides (decision_override == 1) are preserved across regenerations.
    """
    doc = frappe.get_doc("Student Promotion", doc_name)

    ann_name = frappe.db.get_value(
        "Annual Assessment",
        {"academic_year": doc.academic_year, "class_group": doc.class_group},
        "name",
    )
    if not ann_name:
        return {"error": "no_annual_assessment"}

    ann_rows = frappe.get_all(
        "Annual Assessment Row",
        filters={"parent": ann_name},
        fields=["student", "final_grade", "result"],
    )
    if not ann_rows:
        return {"error": "no_rows"}

    # School class configuration
    sc = frappe.db.get_value(
        "School Class",
        doc.school_class,
        ["class_level", "education_level", "minimum_passing_grade"],
        as_dict=True,
    ) or {}
    min_grade = sc.get("minimum_passing_grade") or 10.0
    is_final = _is_final_class(doc.school_class)
    next_sc_name = _get_next_school_class(
        sc.get("class_level", 0), sc.get("education_level", "")
    )

    # Per-student grade aggregation
    student_data: dict = {}
    for row in ann_rows:
        d = student_data.setdefault(row.student, {"grades": [], "failed": 0})
        grade = row.final_grade
        if grade is not None:
            d["grades"].append(grade)
            if grade < min_grade:
                d["failed"] += 1
        elif row.result == "Reprovado":
            # result set manually without a grade value
            d["failed"] += 1

    # Preserve existing manual overrides (saved to DB)
    overrides = {}
    for existing_row in doc.promotion_rows:
        if existing_row.decision_override:
            overrides[existing_row.student] = {
                "decision": existing_row.decision,
                "override_reason": existing_row.override_reason,
                "next_school_class": existing_row.next_school_class,
                "next_class_group": existing_row.next_class_group,
            }

    def _suggest_next_cg(next_sc):
        """Return the first active Class Group for next_sc in next_academic_year."""
        if not next_sc or not doc.next_academic_year:
            return None
        candidates = frappe.get_all(
            "Class Group",
            filters={
                "school_class": next_sc,
                "academic_year": doc.next_academic_year,
                "is_active": 1,
            },
            fields=["name"],
            limit=1,
        )
        return candidates[0].name if candidates else None

    result_rows = []
    for student in sorted(student_data):
        d = student_data[student]
        failed_count = d["failed"]
        grades = d["grades"]
        avg = round(sum(grades) / len(grades), 2) if grades else 0.0

        # Decision logic
        if failed_count == 0 and is_final:
            decision = "Concluído"
        elif failed_count == 0:
            decision = "Promovido"
        elif avg >= 8.0 and avg < min_grade:
            decision = "Recurso"
        else:
            decision = "Retido"

        # Suggest next-year placement only for students moving forward
        if decision == "Promovido":
            next_sc = next_sc_name
            next_cg = _suggest_next_cg(next_sc)
        else:
            next_sc = None
            next_cg = None

        row_data = {
            "student": student,
            "total_failed_subjects": failed_count,
            "decision": decision,
            "next_school_class": next_sc,
            "next_class_group": next_cg,
            "decision_override": 0,
            "override_reason": "",
            "remarks": "",
        }

        # Restore manual override if one was saved
        if student in overrides:
            override = overrides[student]
            row_data.update({
                "decision": override["decision"],
                "override_reason": override["override_reason"] or "",
                "next_school_class": override["next_school_class"],
                "next_class_group": override["next_class_group"],
                "decision_override": 1,
            })

        result_rows.append(row_data)

    return result_rows


@frappe.whitelist()
def generate_next_year_enrollments(promotion_name):
    """
    Create Student Group Assignment + Inscricao for every Promovido/Concluído student.
    Requires status == "Finalizado" and next_academic_year to be set.
    Idempotent: skips students who already have an active SGA for next_academic_year.
    """
    doc = frappe.get_doc("Student Promotion", promotion_name)

    if not doc.next_academic_year:
        frappe.throw(_("Defina o Ano Lectivo Seguinte antes de gerar inscrições."))

    if doc.status != "Finalizado":
        frappe.throw(
            _("A Promoção de Alunos deve estar com estado <b>Finalizado</b> "
              "antes de gerar inscrições. Estado actual: <b>{0}</b>.").format(
                doc.status or "Rascunho"
            ),
            title=_("Estado incorrecto"),
        )

    today = frappe.utils.today()
    created, skipped, errors = 0, 0, []

    for row in doc.promotion_rows:
        if row.decision not in ("Promovido", "Concluído"):
            skipped += 1
            continue

        if not row.next_class_group:
            errors.append(
                _("{0}: sem Nova Turma definida — linha ignorada.").format(row.student)
            )
            continue

        # Idempotency: skip if already has active SGA for next year
        if frappe.db.exists(
            "Student Group Assignment",
            {"student": row.student, "academic_year": doc.next_academic_year, "status": "Activa"},
        ):
            skipped += 1
            continue

        try:
            frappe.get_doc({
                "doctype": "Student Group Assignment",
                "student": row.student,
                "academic_year": doc.next_academic_year,
                "school_class": row.next_school_class,
                "class_group": row.next_class_group,
                "assignment_date": today,
                "status": "Activa",
                "notes": _("Criado automaticamente pela Promoção {0}.").format(doc.name),
            }).insert(ignore_permissions=True)
            created += 1

        except Exception as e:
            errors.append(f"{row.student}: {str(e)}")

    frappe.db.commit()
    return {"created": created, "skipped": skipped, "errors": errors}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_final_class(school_class_name):
    """Return True when no higher class_level exists within the same education_level."""
    sc = frappe.db.get_value(
        "School Class",
        school_class_name,
        ["class_level", "education_level"],
        as_dict=True,
    )
    if not sc:
        return False
    higher = frappe.db.exists(
        "School Class",
        {
            "education_level": sc.education_level,
            "class_level": (">", sc.class_level),
            "is_active": 1,
        },
    )
    return not higher


def _get_next_school_class(class_level, education_level):
    """Return the name of the School Class at class_level + 1 in the same education_level."""
    if not class_level or not education_level:
        return None
    return frappe.db.get_value(
        "School Class",
        {
            "education_level": education_level,
            "class_level": class_level + 1,
            "is_active": 1,
        },
        "name",
    )


# ---------------------------------------------------------------------------
# Document class
# ---------------------------------------------------------------------------

class StudentPromotion(Document):
    def validate(self):
        self._validate_class_group_compatibility()
        self._validate_uniqueness()
        self._validate_annual_assessment_exists()

    def _validate_class_group_compatibility(self):
        if not self.class_group:
            return
        cg = frappe.db.get_value(
            "Class Group",
            self.class_group,
            ["academic_year", "school_class"],
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
                title=_("Classe incompatível"),
            )

    def _validate_uniqueness(self):
        existing = frappe.db.get_value(
            "Student Promotion",
            {
                "academic_year": self.academic_year,
                "class_group": self.class_group,
                "name": ("!=", self.name),
            },
            "name",
        )
        if existing:
            frappe.throw(
                _("Já existe uma Promoção de Alunos para a Turma <b>{0}</b> "
                  "no Ano Lectivo <b>{1}</b>: <b>{2}</b>.").format(
                    self.class_group, self.academic_year, existing
                ),
                title=_("Promoção duplicada"),
            )

    def _validate_annual_assessment_exists(self):
        if not (self.academic_year and self.class_group):
            return
        ann = frappe.db.get_value(
            "Annual Assessment",
            {
                "academic_year": self.academic_year,
                "class_group": self.class_group,
            },
            "name",
        )
        if not ann:
            frappe.throw(
                _("Não existe uma Avaliação Anual para a Turma <b>{0}</b> "
                  "no Ano Lectivo <b>{1}</b>. Crie e calcule a Avaliação Anual "
                  "antes de gerar a Promoção.").format(
                    self.class_group, self.academic_year
                ),
                title=_("Avaliação Anual em falta"),
            )
