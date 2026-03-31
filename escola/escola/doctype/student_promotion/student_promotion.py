import frappe
from frappe import _
from frappe.model.document import Document


@frappe.whitelist()
def generate_promotion(doc_name):
    """
    Load promotion decisions from Annual Assessment.

    Decision per student:
    - Aprovado  → result == "Aprovado" and next_class exists
    - Concluído → result == "Aprovado" and no next_class (final class)
    - Reprovado → result == "Reprovado" (stays in same class)
    """
    doc = frappe.get_doc("Student Promotion", doc_name)

    ann_name = frappe.db.get_value(
        "Annual Assessment",
        {"academic_year": doc.academic_year, "class_group": doc.class_group},
        "name",
    )
    if not ann_name:
        return {"error": "no_annual_assessment"}

    ann_rows = frappe.db.get_all(
        "Annual Assessment Row",
        filters={"parent": ann_name},
        fields=["student", "final_grade", "result"],
        order_by="student asc",
    )
    if not ann_rows:
        return {"error": "no_rows"}

    # Determine whether this is the final class (no next_class pointer)
    next_class = frappe.db.get_value("School Class", doc.school_class, "next_class")
    is_final = not next_class

    result_rows = []
    for row in ann_rows:
        aa_result = (row.result or "").strip()
        if aa_result == "Aprovado":
            decision = "Concluído" if is_final else "Aprovado"
        else:
            decision = "Reprovado"

        result_rows.append({
            "student":     row.student,
            "final_grade": row.final_grade,
            "decision":    decision,
            "remarks":     "",
        })

    return result_rows


@frappe.whitelist()
def generate_next_year_enrollments(promotion_name):
    """
    Create Student Group Assignments for the next academic year.

    - Aprovado / Concluído → doc.target_class_group
    - Reprovado            → doc.retained_class_group (same school_class, new year)

    Idempotent: skips students already with an active SGA for next_academic_year.
    """
    doc = frappe.get_doc("Student Promotion", promotion_name)

    if not doc.next_academic_year:
        frappe.throw(_("Defina o Ano Lectivo Seguinte antes de gerar inscrições."))

    if doc.status != "Finalizado":
        frappe.throw(
            _("A Promoção de Alunos deve estar <b>Finalizada</b> antes de "
              "gerar inscrições. Estado actual: <b>{0}</b>.").format(doc.status or "Rascunho"),
            title=_("Estado incorrecto"),
        )

    if not doc.target_class_group and any(
        r.decision in ("Aprovado", "Concluído") for r in doc.promotion_rows
    ):
        frappe.throw(
            _("Defina a <b>Turma dos Aprovados</b> antes de gerar inscrições."),
            title=_("Turma em falta"),
        )

    if not doc.retained_class_group and any(
        r.decision == "Reprovado" for r in doc.promotion_rows
    ):
        frappe.throw(
            _("Defina a <b>Turma dos Reprovados</b> antes de gerar inscrições."),
            title=_("Turma em falta"),
        )

    # Resolve school_class for each target
    target_sc = (
        frappe.db.get_value("Class Group", doc.target_class_group, "school_class")
        if doc.target_class_group else None
    )
    retained_sc = doc.school_class  # Reprovado stays in same class

    today = frappe.utils.today()
    created, skipped, errors = 0, 0, []

    for row in doc.promotion_rows:
        if row.decision in ("Aprovado", "Concluído"):
            target_cg = doc.target_class_group
            sc = target_sc
        elif row.decision == "Reprovado":
            target_cg = doc.retained_class_group
            sc = retained_sc
        else:
            skipped += 1
            continue

        if not target_cg:
            errors.append(_("{0}: sem turma destino — ignorado.").format(row.student))
            continue

        # Skip if already enrolled
        if frappe.db.exists(
            "Student Group Assignment",
            {
                "student":       row.student,
                "academic_year": doc.next_academic_year,
                "status":        "Activa",
            },
        ):
            skipped += 1
            continue

        try:
            frappe.get_doc({
                "doctype":         "Student Group Assignment",
                "student":         row.student,
                "academic_year":   doc.next_academic_year,
                "school_class":    sc,
                "class_group":     target_cg,
                "assignment_date": today,
                "status":          "Activa",
                "notes": _("Criado automaticamente pela Promoção {0}.").format(doc.name),
            }).insert(ignore_permissions=True)
            created += 1
        except Exception as e:
            errors.append(f"{row.student}: {e}")

    frappe.db.commit()
    return {"created": created, "skipped": skipped, "errors": errors}


class StudentPromotion(Document):
    def validate(self):
        self._validate_class_group_compatibility()
        self._validate_uniqueness()
        self._validate_annual_assessment_exists()

    def _validate_class_group_compatibility(self):
        if not self.class_group:
            return
        cg = frappe.db.get_value(
            "Class Group", self.class_group,
            ["academic_year", "school_class"], as_dict=True,
        )
        if not cg:
            return
        if cg.academic_year != self.academic_year:
            frappe.throw(
                _("A Turma <b>{0}</b> pertence ao Ano Lectivo <b>{1}</b>, "
                  "não ao Ano Lectivo <b>{2}</b>.").format(
                    self.class_group, cg.academic_year, self.academic_year),
                title=_("Turma incompatível"),
            )
        if self.school_class and cg.school_class != self.school_class:
            frappe.throw(
                _("A Turma <b>{0}</b> pertence à Classe <b>{1}</b>, "
                  "não à Classe <b>{2}</b>.").format(
                    self.class_group, cg.school_class, self.school_class),
                title=_("Classe incompatível"),
            )

    def _validate_uniqueness(self):
        existing = frappe.db.get_value(
            "Student Promotion",
            {
                "academic_year": self.academic_year,
                "class_group":   self.class_group,
                "name":          ("!=", self.name),
            },
            "name",
        )
        if existing:
            frappe.throw(
                _("Já existe uma Promoção de Alunos para a Turma <b>{0}</b> "
                  "no Ano Lectivo <b>{1}</b>: <b>{2}</b>.").format(
                    self.class_group, self.academic_year, existing),
                title=_("Promoção duplicada"),
            )

    def _validate_annual_assessment_exists(self):
        if not (self.academic_year and self.class_group):
            return
        ann = frappe.db.get_value(
            "Annual Assessment",
            {"academic_year": self.academic_year, "class_group": self.class_group},
            "name",
        )
        if not ann:
            frappe.throw(
                _("Não existe uma Avaliação Anual para a Turma <b>{0}</b> "
                  "no Ano Lectivo <b>{1}</b>. Crie e calcule a Avaliação Anual primeiro.").format(
                    self.class_group, self.academic_year),
                title=_("Avaliação Anual em falta"),
            )
