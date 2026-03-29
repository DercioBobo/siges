import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate


class StudentFeeAssignment(Document):
    def after_insert(self):
        if self.student and not self.customer:
            customer = _ensure_customer(self.student)
            self.db_set("customer", customer)

    def validate(self):
        self._validate_uniqueness()
        self._validate_has_lines()
        self._validate_dates()
        self._validate_line_amounts()
        self._validate_no_duplicate_lines()

    def _validate_uniqueness(self):
        if not self.is_active:
            return
        existing = frappe.db.get_value(
            "Student Fee Assignment",
            {
                "student": self.student,
                "academic_year": self.academic_year,
                "is_active": 1,
                "name": ("!=", self.name),
            },
            "name",
        )
        if existing:
            frappe.throw(
                _("Já existe uma Atribuição de Propinas activa ({0}) para o aluno {1} "
                  "no ano lectivo {2}.").format(existing, self.student, self.academic_year)
            )

    def _validate_has_lines(self):
        if not self.assignment_lines:
            frappe.throw(_("A Atribuição de Propinas deve ter pelo menos um item de cobrança."))

    def _validate_dates(self):
        if self.start_date and self.end_date and getdate(self.end_date) <= getdate(self.start_date):
            frappe.throw(_("A Data de Fim de Cobrança deve ser posterior ao Início."))

    def _validate_line_amounts(self):
        for line in self.assignment_lines:
            if line.amount <= 0:
                frappe.throw(
                    _("O valor do item '{0}' deve ser maior que zero.").format(
                        line.fee_category or line.item_code
                    )
                )

    def _validate_no_duplicate_lines(self):
        seen = set()
        for line in self.assignment_lines:
            key = (line.fee_category, line.item_code, line.billing_mode)
            if key in seen:
                frappe.throw(
                    _("A combinação Categoria '{0}' + Item '{1}' + Modo '{2}' "
                      "está duplicada na Atribuição.").format(
                        line.fee_category, line.item_code, line.billing_mode
                    )
                )
            seen.add(key)


# ---------------------------------------------------------------------------
# Shared customer helper — used by this module and billing_cycle
# ---------------------------------------------------------------------------

def _ensure_customer(student_name):
    """
    Return the ERPNext Customer name for this student, creating one if needed.
    Safe to call multiple times — never creates duplicates.
    """
    # Try to find a Customer already linked to this student via custom field
    try:
        existing = frappe.db.get_value(
            "Customer",
            {"escola_student": student_name},
            "name",
        )
        if existing:
            return existing
    except Exception:
        pass

    student = (
        frappe.db.get_value(
            "Student", student_name, ["full_name", "student_code"], as_dict=True
        )
        or frappe._dict()
    )
    full_name = student.get("full_name") or student_name

    customer = frappe.new_doc("Customer")
    customer.customer_name = full_name
    customer.customer_type = "Individual"
    customer.customer_group = (
        frappe.db.get_single_value("Selling Settings", "customer_group")
        or "All Customer Groups"
    )
    customer.territory = (
        frappe.db.get_single_value("Selling Settings", "territory")
        or "All Territories"
    )

    # Link back to the student via the custom field (graceful if not yet created)
    try:
        customer.escola_student = student_name
    except Exception:
        pass

    customer.insert(ignore_permissions=False)
    return customer.name


# ---------------------------------------------------------------------------
# Whitelisted API
# ---------------------------------------------------------------------------

@frappe.whitelist()
def load_from_structure(doc_name):
    """
    Load assignment_lines from the selected fee_structure.
    Returns a list of line dicts ready to be inserted into the child table.
    The billing_mode on each line inherits the structure's billing_frequency.
    """
    doc = frappe.get_doc("Student Fee Assignment", doc_name)

    if not doc.fee_structure:
        return {"error": "no_structure"}

    structure = frappe.get_doc("Fee Structure", doc.fee_structure)

    if not structure.fee_lines:
        return {"error": "no_lines"}

    lines = [
        {
            "fee_category": fl.fee_category,
            "item_code": fl.item_code,
            "description": fl.description or "",
            "amount": fl.amount,
            "billing_mode": structure.billing_frequency,
            "is_optional": 0,
        }
        for fl in structure.fee_lines
    ]

    return {"lines": lines}


@frappe.whitelist()
def ensure_customer(doc_name):
    """
    Create or find the ERPNext Customer for the student on this assignment,
    then persist the customer link on the assignment.
    """
    doc = frappe.get_doc("Student Fee Assignment", doc_name)

    if not doc.student:
        return {"error": "no_student"}

    customer = _ensure_customer(doc.student)
    frappe.db.set_value("Student Fee Assignment", doc.name, "customer", customer)

    return {"customer": customer}
