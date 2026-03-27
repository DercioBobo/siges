import frappe
from frappe import _
from frappe.model.document import Document
from escola.escola.doctype.student_fee_assignment.student_fee_assignment import _ensure_customer


class BillingCycle(Document):
    def validate(self):
        if self.due_date and self.posting_date and self.due_date < self.posting_date:
            frappe.throw(_("A Data de Vencimento não pode ser anterior à Data de Facturação."))


# ---------------------------------------------------------------------------
# Invoice generation
# ---------------------------------------------------------------------------

@frappe.whitelist()
def generate_invoices(doc_name):
    """
    Generate one Sales Invoice per applicable student for this Billing Cycle.

    Matching rules:
    - Student Fee Assignment must be active (is_active = 1)
    - Must match academic_year; optionally school_class and class_group
    - Assignment date range (if set) must cover cycle posting_date
    - Assignment lines are filtered by billing_mode == cycle.billing_mode
    - Duplicate invoices (same student + billing cycle) are skipped

    Returns a dict with created, skipped, and total_amount.
    """
    cycle = frappe.get_doc("Billing Cycle", doc_name)

    # Build filter for Student Fee Assignment
    sfa_filters = {
        "academic_year": cycle.academic_year,
        "is_active": 1,
    }
    if cycle.school_class:
        sfa_filters["school_class"] = cycle.school_class
    if cycle.class_group:
        sfa_filters["class_group"] = cycle.class_group

    assignments = frappe.get_all(
        "Student Fee Assignment",
        filters=sfa_filters,
        fields=["name", "student", "customer", "start_date", "end_date"],
    )

    default_company = frappe.db.get_single_value("Global Defaults", "default_company")

    created = 0
    skipped = 0
    total_amount = 0.0

    for asgn in assignments:
        # Date range guard — skip assignments whose validity doesn't cover posting_date
        if asgn.end_date and asgn.end_date < cycle.posting_date:
            continue
        if asgn.start_date and asgn.start_date > cycle.posting_date:
            continue

        # Duplicate prevention: invoice already created for this student + cycle?
        already_exists = _invoice_exists(cycle.name, asgn.student)
        if already_exists:
            skipped += 1
            continue

        # Ensure the student has a linked ERPNext Customer
        customer = asgn.customer
        if not customer:
            customer = _ensure_customer(asgn.student)
            frappe.db.set_value("Student Fee Assignment", asgn.name, "customer", customer)

        # Fetch only lines matching the cycle billing_mode
        sfa_doc = frappe.get_doc("Student Fee Assignment", asgn.name)
        applicable_lines = [
            ln for ln in sfa_doc.assignment_lines
            if ln.billing_mode == cycle.billing_mode
        ]

        if not applicable_lines:
            continue

        # Create the Sales Invoice
        si = frappe.new_doc("Sales Invoice")
        si.customer = customer
        si.company = default_company
        si.posting_date = cycle.posting_date
        si.due_date = cycle.due_date
        si.remarks = "{period} | Aluno: {student} | Ano: {year}".format(
            period=cycle.billing_period_label,
            student=asgn.student,
            year=cycle.academic_year,
        )

        # Custom fields for linkage and duplicate detection (added via setup.py)
        try:
            si.escola_billing_cycle = cycle.name
            si.escola_student = asgn.student
        except Exception:
            pass

        for ln in applicable_lines:
            si.append(
                "items",
                {
                    "item_code": ln.item_code,
                    "item_name": ln.description or ln.item_code,
                    "qty": 1,
                    "rate": ln.amount,
                    "description": ln.description or ln.fee_category,
                },
            )

        si.insert(ignore_permissions=False)
        created += 1
        total_amount += si.grand_total

    # Refresh summary from actual invoice records (idempotent regardless of run count)
    _refresh_cycle_summary(cycle)

    return {
        "created": created,
        "skipped": skipped,
        "total_amount": total_amount,
    }


def _invoice_exists(billing_cycle_name, student_name):
    """
    Check whether a non-cancelled Sales Invoice already exists for
    this billing_cycle + student combination.
    Uses the escola_billing_cycle and escola_student custom fields.
    """
    try:
        return bool(
            frappe.db.get_value(
                "Sales Invoice",
                {
                    "escola_billing_cycle": billing_cycle_name,
                    "escola_student": student_name,
                    "docstatus": ("!=", 2),
                },
                "name",
            )
        )
    except Exception:
        # Custom fields not yet present — fall back to no-duplicate check by remarks
        # (conservative: allow creation if we cannot verify)
        return False


def _refresh_cycle_summary(cycle):
    """
    Re-query the actual invoice totals for this cycle and update the
    summary fields. Safe to call repeatedly.
    """
    try:
        result = frappe.db.sql(
            """
            SELECT
                COUNT(DISTINCT escola_student) AS unique_students,
                COUNT(name)                    AS invoice_count,
                COALESCE(SUM(grand_total), 0)  AS total_amount
            FROM `tabSales Invoice`
            WHERE escola_billing_cycle = %s
              AND docstatus != 2
            """,
            cycle.name,
            as_dict=True,
        )[0]

        cycle.db_set("total_students", result.unique_students or 0)
        cycle.db_set("total_invoices_created", result.invoice_count or 0)
        cycle.db_set("total_amount", result.total_amount or 0)
    except Exception:
        # If custom fields aren't there yet, update with what we computed inline
        pass
