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
    settings = frappe.get_single("School Settings")

    _MESES = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
              "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
    # Use the end of the billing period (due_date) as the reference month, since a
    # cycle spanning e.g. 25/06 - 10/07 bills for July, not June.
    reference_date = cycle.due_date or cycle.posting_date
    mes_referencia = _MESES[getdate(reference_date).month - 1] if reference_date else ""

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
            si.escola_mes_referencia = mes_referencia
            si.escola_encarregado = frappe.db.get_value("Student", sga.student, "primary_guardian")
        except Exception:
            pass

        for ln in applicable_lines:
            base_description = ln.description or ln.item_code
            row_label = "{0} - {1}".format(base_description, mes_referencia) if mes_referencia else base_description
            si.append(
                "items",
                {
                    "item_code": ln.item_code,
                    "item_name": row_label,
                    "qty": 1,
                    "rate": ln.amount,
                    "description": row_label,
                },
            )

        sibling_discount = _get_sibling_discount(sga.student, cycle.academic_year, settings)
        if sibling_discount:
            si.additional_discount_percentage = sibling_discount

        si.insert(ignore_permissions=True)
        if auto_submit:
            si.submit()
        created += 1
        total_amount += si.grand_total

    # --- Phase 3: create addon invoices for students with active extras ---
    sibling_discount_addon = int(settings.get("sibling_discount_applies_to_addons") or 0)
    default_fee_item = frappe.db.get_single_value("School Settings", "default_fee_item_code") or "Propina"
    addon_created = 0
    addon_amount = 0.0
    addon_errors = []

    for sga in sgAs:
        extras = _get_active_extras(sga.student, cycle.posting_date)
        if not extras:
            continue

        if _addon_invoice_exists(sga.student, cycle.posting_date):
            continue

        # Re-use customer from Phase 1 or look it up
        customer = customer_map.get(sga.student)
        if not customer:
            try:
                customer = ensure_customer_for_student(sga.student)
            except Exception as e:
                addon_errors.append(_("Extras — cliente não criado para {0}: {1}").format(sga.student, str(e)))
                continue

        si = frappe.new_doc("Sales Invoice")
        si.customer = customer
        si.company = default_company
        si.posting_date = cycle.posting_date
        si.due_date = cycle.due_date
        si.remarks = "Extras Mensais | Aluno: {student} | Ano: {year}".format(
            student=sga.student,
            year=cycle.academic_year or "",
        )

        try:
            si.escola_billing_cycle = cycle.name
            si.escola_student = sga.student
            si.escola_mes_referencia = mes_referencia
            si.escola_encarregado = frappe.db.get_value("Student", sga.student, "primary_guardian")
            si.escola_is_addon_invoice = 1
        except Exception:
            pass

        for ext in extras:
            item_code = ext.get("item_code") or default_fee_item
            row_label = "{svc} - {mes}".format(svc=ext["service_name"], mes=mes_referencia) if mes_referencia else ext["service_name"]
            si.append("items", {
                "item_code": item_code,
                "item_name": row_label,
                "qty": 1,
                "rate": ext["current_amount"],
                "description": row_label,
            })

        if sibling_discount_addon:
            disc = _get_sibling_discount(sga.student, cycle.academic_year, settings)
            if disc:
                si.additional_discount_percentage = disc

        try:
            si.insert(ignore_permissions=True)
            if auto_submit:
                si.submit()
            addon_created += 1
            addon_amount += si.grand_total
        except Exception as e:
            addon_errors.append("Extras {0}: {1}".format(sga.student, str(e)))

    _refresh_cycle_summary(cycle)

    if created > 0 or addon_created > 0:
        cycle.db_set("status", "Gerado")
        if cycle.billing_schedule:
            frappe.db.set_value(
                "Billing Schedule", cycle.billing_schedule,
                "last_billed_date", cycle.posting_date,
            )
    elif skipped > 0 and created == 0 and not pre_errors:
        # All students were legitimately skipped (advance payments / already billed).
        # Mark the cycle so it doesn't appear as a forgotten draft.
        cycle.db_set("status", "Sem Facturas")

    all_errors = pre_errors + addon_errors
    cycle.db_set("skipped_count", skipped)
    cycle.db_set("error_count", len(all_errors))
    cycle.db_set("generation_errors", "\n".join(all_errors) if all_errors else "")

    return {
        "created": created,
        "skipped": skipped,
        "total_amount": total_amount,
        "addon_created": addon_created,
        "addon_amount": addon_amount,
        "errors": all_errors,
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
    """Return the single active Fee Structure for a class."""
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
    in the same billing period, across any cycle OR via an advance payment.
    Uses period-based matching (month/quarter/year).
    """
    mode = cycle.billing_mode
    date = cycle.posting_date

    if mode == "Mensal":
        period_sql = "YEAR(si.posting_date) = YEAR(%s) AND MONTH(si.posting_date) = MONTH(%s)"
        params = (student_name, mode, date, date)
        adv_sql = "YEAR(apl.posting_date) = YEAR(%s) AND MONTH(apl.posting_date) = MONTH(%s)"
        adv_params = (student_name, mode, date, date)
    elif mode == "Trimestral":
        period_sql = "YEAR(si.posting_date) = YEAR(%s) AND QUARTER(si.posting_date) = QUARTER(%s)"
        params = (student_name, mode, date, date)
        adv_sql = "YEAR(apl.posting_date) = YEAR(%s) AND QUARTER(apl.posting_date) = QUARTER(%s)"
        adv_params = (student_name, mode, date, date)
    elif mode == "Anual":
        period_sql = "YEAR(si.posting_date) = YEAR(%s)"
        params = (student_name, mode, date)
        adv_sql = "YEAR(apl.posting_date) = YEAR(%s)"
        adv_params = (student_name, mode, date)
    else:
        period_sql = "si.posting_date = %s"
        params = (student_name, mode, date)
        adv_sql = "apl.posting_date = %s"
        adv_params = (student_name, mode, date)

    try:
        if frappe.db.sql(
            f"""
            SELECT si.name
            FROM `tabSales Invoice` si
            JOIN `tabBilling Cycle` bc ON bc.name = si.escola_billing_cycle
            WHERE si.escola_student = %s
              AND si.docstatus != 2
              AND COALESCE(si.escola_is_addon_invoice, 0) = 0
              AND bc.billing_mode = %s
              AND {period_sql}
            LIMIT 1
            """,
            params,
        ):
            return True

        # Also block if an active advance payment already covers this period
        if frappe.db.sql(
            f"""
            SELECT 1
            FROM `tabAdiantamento Period Line` apl
            JOIN `tabAdiantamento De Pagamento` adp ON adp.name = apl.parent
            WHERE adp.student = %s
              AND adp.docstatus = 1
              AND apl.billing_mode = %s
              AND {adv_sql}
            LIMIT 1
            """,
            adv_params,
        ):
            return True

        return False
    except Exception:
        return False


def _get_sibling_discount(student, academic_year, settings):
    """
    Returns the sibling discount percent if the student's guardian has >= threshold
    active students enrolled in this academic year. Returns 0 otherwise.
    """
    if not int(settings.get("sibling_discount_enabled") or 0):
        return 0

    guardian = frappe.db.get_value("Student", student, "primary_guardian")
    if not guardian:
        return 0

    threshold = int(settings.get("sibling_discount_threshold") or 3)

    try:
        count = frappe.db.sql(
            """
            SELECT COUNT(DISTINCT s.name)
            FROM `tabStudent` s
            JOIN `tabStudent Group Assignment` sga ON sga.student = s.name
            WHERE s.primary_guardian = %s
              AND s.current_status = 'Activo'
              AND sga.academic_year = %s
              AND sga.status = 'Activa'
            """,
            (guardian, academic_year),
        )[0][0]
    except Exception:
        return 0

    if count >= threshold:
        return float(settings.get("sibling_discount_percent") or 10)

    return 0


def _get_active_extras(student, posting_date):
    """Return active extras for a student on the given posting_date."""
    date = getdate(posting_date)
    mea_name = frappe.db.get_value("Mensalidade Extra do Aluno", {"student": student}, "name")
    if not mea_name:
        return []

    try:
        rows = frappe.db.sql(
            """
            SELECT
                l.service,
                se.service_name,
                se.current_amount,
                se.item_code
            FROM `tabLinha de Mensalidade Extra` l
            JOIN `tabServico Extra` se ON se.name = l.service
            WHERE l.parent = %s
              AND l.status = 'Activo'
              AND l.start_date <= %s
              AND (l.end_date IS NULL OR l.end_date >= %s)
            """,
            (mea_name, date, date),
            as_dict=True,
        )
        for r in rows:
            r["current_amount"] = float(r["current_amount"] or 0)
        return rows
    except Exception:
        return []


def _addon_invoice_exists(student, posting_date):
    """Check if a non-cancelled addon invoice already exists for this student/month."""
    date = posting_date
    try:
        result = frappe.db.sql(
            """
            SELECT si.name
            FROM `tabSales Invoice` si
            WHERE si.escola_student = %s
              AND si.escola_is_addon_invoice = 1
              AND si.docstatus != 2
              AND YEAR(si.posting_date) = YEAR(%s)
              AND MONTH(si.posting_date) = MONTH(%s)
            LIMIT 1
            """,
            (student, date, date),
        )
        return bool(result)
    except Exception:
        return False


def _refresh_cycle_summary(cycle):
    """Re-query actual invoice totals for this cycle and update summary fields."""
    try:
        result = frappe.db.sql(
            """
            SELECT
                COUNT(DISTINCT CASE WHEN COALESCE(escola_is_addon_invoice, 0) = 0 THEN escola_student END) AS unique_students,
                SUM(CASE WHEN COALESCE(escola_is_addon_invoice, 0) = 0 THEN 1 ELSE 0 END)                  AS invoice_count,
                COALESCE(SUM(CASE WHEN COALESCE(escola_is_addon_invoice, 0) = 0 THEN grand_total ELSE 0 END), 0) AS total_amount,
                SUM(CASE WHEN escola_is_addon_invoice = 1 THEN 1 ELSE 0 END)                                AS addon_count,
                COALESCE(SUM(CASE WHEN escola_is_addon_invoice = 1 THEN grand_total ELSE 0 END), 0)         AS addon_amount
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
        cycle.db_set("total_addon_invoices_created", result.addon_count or 0)
        cycle.db_set("total_addon_amount", result.addon_amount or 0)
    except Exception:
        pass
