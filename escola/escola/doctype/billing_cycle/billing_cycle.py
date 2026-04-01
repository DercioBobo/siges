import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate
from escola.escola.doctype.student.student import ensure_customer_for_student


class BillingCycle(Document):
    def validate(self):
        if self.due_date and self.posting_date and getdate(self.due_date) < getdate(self.posting_date):
            frappe.throw(_("A Data de Vencimento não pode ser anterior à Data de Facturação."))

        if self.school_class and self.billing_mode:
            _validate_fee_structure_compatibility(self.school_class, self.billing_mode)


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

    sgAs = frappe.get_all(
        "Student Group Assignment",
        filters=sga_filters,
        fields=["student", "class_group"],
    )

    default_company = frappe.db.get_single_value("Global Defaults", "default_company")
    auto_submit = frappe.db.get_single_value("School Settings", "auto_submit_invoices") or 0

    # --- Phase 1: pre-create all customers before touching invoices ---
    # A customer failure skips that student but never leaves invoices in a partial state.
    customer_map = {}
    pre_errors = []
    for sga in sgAs:
        if _invoice_exists(cycle, sga.student):
            continue
        try:
            customer_map[sga.student] = ensure_customer_for_student(sga.student)
        except Exception as e:
            pre_errors.append(_("Cliente não criado para {0}: {1}").format(sga.student, str(e)))

    # --- Phase 2: create invoices only for students with a valid customer ---
    created = 0
    skipped = 0
    total_amount = 0.0

    for sga in sgAs:
        if _invoice_exists(cycle, sga.student):
            skipped += 1
            continue

        customer = customer_map.get(sga.student)
        if not customer:
            skipped += 1
            continue

        si = frappe.new_doc("Sales Invoice")
        si.customer = customer
        si.company = default_company
        si.posting_date = cycle.posting_date
        si.due_date = cycle.due_date
        si.remarks = "{mode} | Aluno: {student} | Ano: {year}".format(
            mode=cycle.billing_mode or "",
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
        "errors": pre_errors,
    }


def _validate_fee_structure_compatibility(school_class, billing_mode):
    """
    Warn early (on save) if no active Fee Structure has lines matching this billing_mode.
    Raises a non-blocking msgprint (alert) rather than a hard throw so the user can still
    save a draft cycle and fix the Fee Structure before generating invoices.
    """
    fs_name = frappe.db.get_value(
        "Fee Structure",
        {"school_class": school_class, "is_active": 1},
        "name",
    )
    if not fs_name:
        frappe.msgprint(
            _("Aviso: Não existe um Plano de Propinas activo para a Classe <b>{0}</b>. "
              "Crie um antes de gerar facturas.").format(school_class),
            title=_("Plano de Propinas em falta"),
            indicator="orange",
        )
        return

    has_lines = frappe.db.exists(
        "Fee Structure Line",
        {"parent": fs_name, "billing_mode": billing_mode},
    )
    if not has_lines:
        frappe.msgprint(
            _("Aviso: O Plano de Propinas <b>{0}</b> não tem linhas com o Modo de Cobrança "
              "<b>{1}</b>. Adicione as linhas correspondentes antes de gerar facturas.").format(
                fs_name, billing_mode
            ),
            title=_("Modo de Cobrança sem linhas"),
            indicator="orange",
        )


def _find_fee_structure(school_class, academic_year=None):
    """Find the single active Fee Structure for a class."""
    return frappe.db.get_value(
        "Fee Structure",
        {"school_class": school_class, "is_active": 1},
        "name",
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
    affected_students = set()

    for inv in invoices:
        student = frappe.db.get_value("Sales Invoice", inv.name, "escola_student")
        if student:
            affected_students.add(student)
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

    # Recalculate financial status for all affected students.
    # Necessary because deleted draft invoices don't fire the on_cancel hook.
    from escola.escola.doctype.billing_cycle.penalty import update_student_financial_status
    for student in affected_students:
        try:
            update_student_financial_status(student)
        except Exception:
            pass

    frappe.db.commit()

    return {"cancelled": cancelled, "deleted": deleted, "errors": errors}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _invoice_exists(cycle, student_name):
    """
    Check whether a non-cancelled invoice already exists for this student
    with the same billing_mode and posting_date, across any cycle.
    Prevents duplicates when two cycles are created for the same period.
    """
    try:
        return bool(frappe.db.sql(
            """
            SELECT si.name
            FROM `tabSales Invoice` si
            JOIN `tabBilling Cycle` bc ON bc.name = si.escola_billing_cycle
            WHERE si.escola_student = %s
              AND si.docstatus != 2
              AND bc.billing_mode = %s
              AND si.posting_date = %s
            LIMIT 1
            """,
            (student_name, cycle.billing_mode, cycle.posting_date),
        ))
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
