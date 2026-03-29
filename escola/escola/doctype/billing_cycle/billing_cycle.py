import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate


class BillingCycle(Document):
    def validate(self):
        if self.due_date and self.posting_date and getdate(self.due_date) < getdate(self.posting_date):
            frappe.throw(_("A Data de Vencimento não pode ser anterior à Data de Facturação."))


# ---------------------------------------------------------------------------
# Invoice generation
# ---------------------------------------------------------------------------

@frappe.whitelist()
def generate_invoices(doc_name):
    """
    Generate one Sales Invoice per active student in this Billing Cycle's class/turma.

    Flow:
    1. Find the active Fee Structure for school_class (year-specific first, then generic)
    2. Filter fee lines by billing_mode == cycle.billing_mode
    3. Find all active Student Group Assignments for that class (optionally filtered by class_group)
    4. Create one draft invoice per student, skipping duplicates

    Returns a dict with created, skipped, and total_amount.
    """
    cycle = frappe.get_doc("Billing Cycle", doc_name)

    if not cycle.school_class:
        frappe.throw(_("Defina a Classe antes de gerar facturas."), title=_("Classe em falta"))

    # --- Find Fee Structure ---
    # Prefer year-specific, fall back to generic (no academic_year)
    fs_name = _find_fee_structure(cycle.school_class, cycle.academic_year)
    if not fs_name:
        frappe.throw(
            _("Não existe um Plano de Propinas activo para a Classe <b>{0}</b>. "
              "Crie um Plano de Propinas activo para esta classe.").format(cycle.school_class),
            title=_("Plano de Propinas em falta"),
        )

    fee_structure = frappe.get_doc("Fee Structure", fs_name)
    applicable_lines = [ln for ln in fee_structure.fee_lines if ln.billing_mode == cycle.billing_mode]

    if not applicable_lines:
        frappe.throw(
            _("O Plano de Propinas <b>{0}</b> não tem linhas com o Modo de Cobrança <b>{1}</b>.").format(
                fs_name, cycle.billing_mode
            ),
            title=_("Sem linhas aplicáveis"),
        )

    # --- Find active students ---
    sga_filters = {
        "school_class": cycle.school_class,
        "status": "Activa",
    }
    if cycle.academic_year:
        sga_filters["academic_year"] = cycle.academic_year
    if cycle.class_group:
        sga_filters["class_group"] = cycle.class_group

    sgAs = frappe.get_all(
        "Student Group Assignment",
        filters=sga_filters,
        fields=["student", "class_group"],
    )

    default_company = frappe.db.get_single_value("Global Defaults", "default_company")
    auto_submit = frappe.db.get_single_value("School Settings", "auto_submit_invoices") or 0

    created = 0
    skipped = 0
    total_amount = 0.0

    for sga in sgAs:
        if _invoice_exists(cycle.name, sga.student):
            skipped += 1
            continue

        customer = _ensure_customer(sga.student)

        si = frappe.new_doc("Sales Invoice")
        si.customer = customer
        si.company = default_company
        si.posting_date = cycle.posting_date
        si.due_date = cycle.due_date
        si.remarks = "{period} | Aluno: {student} | Ano: {year}".format(
            period=cycle.billing_period_label,
            student=sga.student,
            year=cycle.academic_year or "",
        )

        try:
            si.escola_billing_cycle = cycle.name
            si.escola_student = sga.student
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

        si.insert(ignore_permissions=True)
        if auto_submit:
            si.submit()
        created += 1
        total_amount += si.grand_total

    _refresh_cycle_summary(cycle)

    if created > 0:
        cycle.db_set("status", "Gerado")

    return {
        "created": created,
        "skipped": skipped,
        "total_amount": total_amount,
    }


def _find_fee_structure(school_class, academic_year=None):
    """
    Find the active Fee Structure for a class.
    Prefers year-specific match; falls back to a structure with no academic_year set.
    """
    if academic_year:
        name = frappe.db.get_value(
            "Fee Structure",
            {"school_class": school_class, "academic_year": academic_year, "is_active": 1},
            "name",
        )
        if name:
            return name

    # Fall back: active structure with no year restriction
    return frappe.db.get_value(
        "Fee Structure",
        {"school_class": school_class, "is_active": 1},
        "name",
        order_by="creation desc",
    )


# ---------------------------------------------------------------------------
# Cancel cycle
# ---------------------------------------------------------------------------

@frappe.whitelist()
def cancel_cycle(doc_name):
    """
    Cancel all invoices generated by this cycle, then mark the cycle as Cancelado.
    - Draft invoices (docstatus=0) are deleted.
    - Submitted invoices (docstatus=1) are cancelled.
    Already-cancelled invoices (docstatus=2) are ignored.
    """
    cycle = frappe.get_doc("Billing Cycle", doc_name)

    if cycle.status == "Cancelado":
        frappe.throw(_("Este ciclo já está cancelado."), title=_("Já cancelado"))

    try:
        invoices = frappe.get_all(
            "Sales Invoice",
            filters={"escola_billing_cycle": doc_name, "docstatus": ("!=", 2)},
            fields=["name", "docstatus"],
        )
    except Exception:
        invoices = []

    cancelled, deleted, errors = 0, 0, []

    for inv in invoices:
        try:
            if inv.docstatus == 1:
                frappe.get_doc("Sales Invoice", inv.name).cancel()
                cancelled += 1
            else:
                frappe.delete_doc("Sales Invoice", inv.name, ignore_permissions=True)
                deleted += 1
        except Exception as e:
            errors.append(f"{inv.name}: {str(e)}")

    cycle.db_set("status", "Cancelado")
    _refresh_cycle_summary(cycle)
    frappe.db.commit()

    return {"cancelled": cancelled, "deleted": deleted, "errors": errors}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ensure_customer(student_name):
    """
    Return the ERPNext Customer name for this student, creating one if needed.
    Safe to call multiple times — never creates duplicates.
    """
    try:
        existing = frappe.db.get_value("Customer", {"escola_student": student_name}, "name")
        if existing:
            return existing
    except Exception:
        pass

    student = (
        frappe.db.get_value("Student", student_name, ["full_name", "student_code"], as_dict=True)
        or frappe._dict()
    )
    full_name = student.get("full_name") or student_name

    customer = frappe.new_doc("Customer")
    customer.customer_name = full_name
    customer.customer_type = "Individual"
    customer.customer_group = (
        frappe.db.get_single_value("School Settings", "default_customer_group")
        or frappe.db.get_single_value("Selling Settings", "customer_group")
        or "All Customer Groups"
    )
    customer.territory = (
        frappe.db.get_single_value("School Settings", "default_territory")
        or frappe.db.get_single_value("Selling Settings", "territory")
        or "All Territories"
    )

    try:
        customer.escola_student = student_name
    except Exception:
        pass

    customer.insert(ignore_permissions=True)
    return customer.name


def _invoice_exists(billing_cycle_name, student_name):
    """Check whether a non-cancelled Sales Invoice already exists for this billing_cycle + student."""
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
        return False


def _refresh_cycle_summary(cycle):
    """Re-query actual invoice totals for this cycle and update summary fields."""
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
        pass
