import frappe
from frappe import _
from frappe.model.document import Document


class FeeStructure(Document):
    def validate(self):
        self._validate_has_lines()
        self._validate_line_amounts()
        self._validate_line_billing_mode()
        self._validate_no_duplicate_lines()
        self._validate_uniqueness()

    def _validate_has_lines(self):
        if not self.fee_lines:
            frappe.throw(_("O Plano de Propinas deve ter pelo menos um componente de cobrança."))

    def _validate_line_amounts(self):
        for line in self.fee_lines:
            if line.amount <= 0:
                frappe.throw(
                    _("O valor da linha '{0}' deve ser maior que zero.").format(
                        line.fee_category or line.item_code
                    )
                )

    def _validate_line_billing_mode(self):
        for line in self.fee_lines:
            if not line.billing_mode:
                frappe.throw(
                    _("A linha '{0}' não tem Modo de Cobrança definido.").format(
                        line.fee_category or line.item_code
                    )
                )

    def _validate_no_duplicate_lines(self):
        seen = set()
        for line in self.fee_lines:
            key = (line.fee_category, line.item_code, line.billing_mode)
            if key in seen:
                frappe.throw(
                    _("A combinação Categoria '{0}' + Item '{1}' + Modo '{2}' está duplicada no Plano.").format(
                        line.fee_category, line.item_code, line.billing_mode
                    )
                )
            seen.add(key)

    def _validate_uniqueness(self):
        if not self.is_active or not self.school_class:
            return
        existing = frappe.db.get_value(
            "Fee Structure",
            {
                "academic_year": self.academic_year,
                "school_class": self.school_class,
                "is_active": 1,
                "name": ("!=", self.name),
            },
            "name",
        )
        if existing:
            frappe.throw(
                _("Já existe um Plano de Propinas activo para a Classe <b>{0}</b> "
                  "no Ano Lectivo <b>{1}</b>: <b>{2}</b>.").format(
                    self.school_class, self.academic_year, existing
                ),
                title=_("Plano duplicado"),
            )


@frappe.whitelist()
def generate_assignments(fee_structure_name):
    """
    Bulk-create Student Fee Assignments for all active students in the
    fee structure's class + academic year.
    Idempotent: skips students who already have an active SFA for this year.
    """
    fs = frappe.get_doc("Fee Structure", fee_structure_name)

    if not fs.school_class:
        frappe.throw(_("O Plano de Propinas deve ter uma Classe definida."), title=_("Classe em falta"))

    if not fs.fee_lines:
        frappe.throw(_("O Plano de Propinas não tem linhas de cobrança."), title=_("Plano vazio"))

    sgAs = frappe.get_all(
        "Student Group Assignment",
        filters={
            "academic_year": fs.academic_year,
            "school_class": fs.school_class,
            "status": "Activa",
        },
        fields=["student", "class_group"],
    )

    if not sgAs:
        return {"created": 0, "skipped": 0, "errors": []}

    base_lines = [
        {
            "fee_category": fl.fee_category,
            "item_code": fl.item_code,
            "description": fl.description or "",
            "amount": fl.amount,
            "billing_mode": fl.billing_mode,
            "is_custom": 0,
        }
        for fl in fs.fee_lines
    ]

    created, skipped, errors = 0, 0, []

    for sga in sgAs:
        if frappe.db.exists("Student Fee Assignment", {
            "student": sga.student,
            "academic_year": fs.academic_year,
            "is_active": 1,
        }):
            skipped += 1
            continue

        try:
            frappe.get_doc({
                "doctype": "Student Fee Assignment",
                "student": sga.student,
                "academic_year": fs.academic_year,
                "school_class": fs.school_class,
                "class_group": sga.class_group,
                "fee_structure": fs.name,
                "is_active": 1,
                "assignment_lines": base_lines,
            }).insert(ignore_permissions=True)
            created += 1
        except Exception as e:
            errors.append({"student": sga.student, "error": str(e)})

    frappe.db.commit()
    return {"created": created, "skipped": skipped, "errors": errors}
