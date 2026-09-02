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
    force = bool(cycle.get("force_regenerate"))

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

    bolsista_students = set(frappe.get_all("Student", filters={"is_bolsista": 1}, pluck="name"))

    default_company = frappe.db.get_single_value("Global Defaults", "default_company")
    auto_submit = frappe.db.get_single_value("School Settings", "auto_submit_invoices") or 0
    settings = frappe.get_single("School Settings")
    tax_template = settings.sales_taxes_template if settings.get("auto_apply_sales_tax") else None

    _MESES = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
              "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
    # Use the end of the billing period (due_date) as the reference month, since a
    # cycle spanning e.g. 25/06 - 10/07 bills for July, not June.
    reference_date = cycle.due_date or cycle.posting_date
    mes_referencia = _MESES[getdate(reference_date).month - 1] if reference_date else ""

    # --- Per-student generation log ---
    # One entry per student in the turma, updated as we walk through the phases
    # below. Written to the `generation_log` child table at the end so the user
    # can trace exactly why each student did or did not get an invoice.
    outcomes = {}

    def _outcome(sga):
        o = outcomes.get(sga.student)
        if o is None:
            o = {
                "student": sga.student,
                "student_name": frappe.db.get_value("Student", sga.student, "full_name") or sga.student,
                "class_group": sga.class_group,
                "status": "Ignorado",
                "reason": "",
                "sales_invoice": None,
            }
            outcomes[sga.student] = o
        return o

    period_label = mes_referencia or str(cycle.posting_date)

    # --- Phase 1: pre-create all customers before touching invoices ---
    # A customer failure skips that student but never leaves invoices in a partial state.
    customer_map = {}
    pre_errors = []
    for sga in sgAs:
        o = _outcome(sga)
        if sga.student in bolsista_students:
            o["status"] = "Ignorado"
            o["reason"] = _("Aluno bolsista — isento de propinas.")
            continue
        blocking_dt, blocking_name = (None, None) if force else _find_blocking_doc(cycle, sga.student)
        if blocking_dt:
            o["status"] = "Ignorado"
            if blocking_dt == "Sales Invoice":
                o["sales_invoice"] = blocking_name
                o["reason"] = _(
                    "Já existe a factura {0} (não cancelada) para este aluno no período {1} / {2}."
                ).format(blocking_name, cycle.billing_mode, period_label)
            else:
                o["reason"] = _(
                    "Coberto pelo adiantamento {0} no período {1} / {2}."
                ).format(blocking_name, cycle.billing_mode, period_label)
            continue
        try:
            customer_map[sga.student] = ensure_customer_for_student(sga.student)
        except Exception as e:
            pre_errors.append(_("Cliente não criado para {0}: {1}").format(sga.student, str(e)))
            o["status"] = "Erro"
            o["reason"] = _("Falha ao criar/obter o Cliente ERPNext: {0}").format(str(e))

    # --- Phase 2: create invoices only for students with a valid customer ---
    created = 0
    skipped = 0
    total_amount = 0.0

    for sga in sgAs:
        if sga.student in bolsista_students:
            skipped += 1
            continue

        if _invoice_exists(cycle, sga.student, force):
            skipped += 1
            continue

        o = _outcome(sga)
        customer = customer_map.get(sga.student)
        if not customer:
            skipped += 1
            if o["status"] != "Erro":
                o["status"] = "Ignorado"
                o["reason"] = _("Cliente ERPNext não disponível para este aluno.")
            continue

        si = frappe.new_doc("Sales Invoice")
        si.customer = customer
        si.company = default_company
        # set_posting_time = 1 keeps our posting_date — ERPNext otherwise resets
        # it to today() during validate whenever this flag is falsy.
        si.set_posting_time = 1
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

        _apply_sales_tax(si, tax_template)

        # Wrap each invoice in its own savepoint: one bad invoice (e.g. a
        # validation error, a frozen accounting period, a missing item) then
        # skips only that student instead of aborting the whole run and
        # leaving the rest of the turma unbilled.
        savepoint = "si_" + frappe.generate_hash(length=10)
        frappe.db.savepoint(savepoint)
        try:
            si.insert(ignore_permissions=True)
            if auto_submit:
                si.submit()
        except Exception as e:
            frappe.db.rollback(save_point=savepoint)
            skipped += 1
            pre_errors.append(_("Factura não criada para {0}: {1}").format(sga.student, str(e)))
            o["status"] = "Erro"
            o["reason"] = _("Falha ao criar a factura: {0}").format(str(e))
            continue
        else:
            frappe.db.release_savepoint(savepoint)

        created += 1
        total_amount += si.grand_total
        o["status"] = "Factura Criada"
        o["reason"] = _("Factura criada.")
        o["sales_invoice"] = si.name

    # --- Phase 3: create addon invoices for students with active extras ---
    sibling_discount_addon = int(settings.get("sibling_discount_applies_to_addons") or 0)
    default_fee_item = frappe.db.get_single_value("School Settings", "default_fee_item_code") or "Propina"
    addon_created = 0
    addon_amount = 0.0
    addon_errors = []

    for sga in sgAs:
        if sga.student in bolsista_students:
            continue

        extras = _get_active_extras(sga.student, cycle.posting_date)
        if not extras:
            continue

        if _addon_invoice_exists(sga.student, cycle.due_date or cycle.posting_date, force):
            continue

        # Re-use customer from Phase 1 or look it up
        customer = customer_map.get(sga.student)
        if not customer:
            try:
                customer = ensure_customer_for_student(sga.student)
            except Exception as e:
                addon_errors.append(_("Extras — cliente não criado para {0}: {1}").format(sga.student, str(e)))
                _append_outcome_note(_outcome(sga), _("Extras: cliente não criado — {0}").format(str(e)))
                continue

        si = frappe.new_doc("Sales Invoice")
        si.customer = customer
        si.company = default_company
        si.set_posting_time = 1  # keep our posting_date (see phase 2)
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

        _apply_sales_tax(si, tax_template)

        savepoint = "addon_" + frappe.generate_hash(length=10)
        frappe.db.savepoint(savepoint)
        try:
            si.insert(ignore_permissions=True)
            if auto_submit:
                si.submit()
        except Exception as e:
            frappe.db.rollback(save_point=savepoint)
            addon_errors.append("Extras {0}: {1}".format(sga.student, str(e)))
            _append_outcome_note(_outcome(sga), _("Falha na factura de extras: {0}").format(str(e)))
        else:
            frappe.db.release_savepoint(savepoint)
            addon_created += 1
            addon_amount += si.grand_total
            _append_outcome_note(_outcome(sga), _("Factura de extras criada: {0}").format(si.name))

    _write_generation_log(cycle, list(outcomes.values()))
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

    if force:
        cycle.db_set("force_regenerate", 0)

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


def _invoice_exists(cycle, student_name, force=False):
    """
    Check whether a non-cancelled invoice already exists for this student
    in the same billing period, across any cycle OR via an advance payment.

    When force=True this check is bypassed entirely.
    """
    if force:
        return False
    doctype, _name = _find_blocking_doc(cycle, student_name)
    return bool(doctype)


def _find_blocking_doc(cycle, student_name):
    """
    Return ``(doctype, name)`` of the document that already covers this student
    for the cycle's billing *period* — a Sales Invoice or an Adiantamento De
    Pagamento — or ``(None, None)`` if nothing blocks generation.

    The period is identified by the cycle's **reference date** (``due_date``, the
    end of the billing period), NOT the posting date. A cycle routinely posts in
    the month before the one it bills — September propinas are posted on 25
    August — so matching on ``posting_date`` made a September cycle collide with
    the student's August invoice (which also carried an August posting date).

    An existing invoice's own period is taken from the ``due_date`` of the
    Billing Cycle that produced it; an Adiantamento period line's ``posting_date``
    is already the billing month itself.
    """
    mode = cycle.billing_mode
    ref = cycle.due_date or cycle.posting_date

    inv_ref = "COALESCE(bc.due_date, bc.posting_date)"
    adv_ref = "apl.posting_date"

    if mode == "Mensal":
        period_sql = f"YEAR({inv_ref}) = YEAR(%s) AND MONTH({inv_ref}) = MONTH(%s)"
        params = (student_name, mode, ref, ref)
        adv_sql = f"YEAR({adv_ref}) = YEAR(%s) AND MONTH({adv_ref}) = MONTH(%s)"
        adv_params = (student_name, mode, ref, ref)
    elif mode == "Trimestral":
        period_sql = f"YEAR({inv_ref}) = YEAR(%s) AND QUARTER({inv_ref}) = QUARTER(%s)"
        params = (student_name, mode, ref, ref)
        adv_sql = f"YEAR({adv_ref}) = YEAR(%s) AND QUARTER({adv_ref}) = QUARTER(%s)"
        adv_params = (student_name, mode, ref, ref)
    elif mode == "Anual":
        period_sql = f"YEAR({inv_ref}) = YEAR(%s)"
        params = (student_name, mode, ref)
        adv_sql = f"YEAR({adv_ref}) = YEAR(%s)"
        adv_params = (student_name, mode, ref)
    else:
        period_sql = f"{inv_ref} = %s"
        params = (student_name, mode, ref)
        adv_sql = f"{adv_ref} = %s"
        adv_params = (student_name, mode, ref)

    try:
        si_hit = frappe.db.sql(
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
        )
        if si_hit:
            return ("Sales Invoice", si_hit[0][0])

        # Also block if an active advance payment already covers this period
        adv_hit = frappe.db.sql(
            f"""
            SELECT adp.name
            FROM `tabAdiantamento Period Line` apl
            JOIN `tabAdiantamento De Pagamento` adp ON adp.name = apl.parent
            WHERE adp.student = %s
              AND adp.docstatus = 1
              AND apl.billing_mode = %s
              AND {adv_sql}
            LIMIT 1
            """,
            adv_params,
        )
        if adv_hit:
            return ("Adiantamento De Pagamento", adv_hit[0][0])

        return (None, None)
    except Exception:
        # A broken duplicate check must not silently create duplicate invoices
        # nor silently block everyone — log it so it can be traced.
        frappe.log_error(frappe.get_traceback(), _("Billing Cycle: _find_blocking_doc falhou"))
        return (None, None)


def _apply_sales_tax(si, tax_template):
    """
    Apply the School Settings' Sales Taxes and Charges Template to a draft invoice,
    using ERPNext's own tax engine (native tax rows, calculated on save).
    """
    if not tax_template:
        return

    si.taxes_and_charges = tax_template
    si.set_taxes()


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


def _addon_invoice_exists(student, ref_date, force=False):
    """Check if a non-cancelled addon invoice already covers this student's billing period.

    Addon invoices are created with ``due_date = cycle.due_date``, so the period
    is matched on ``due_date`` — not ``posting_date`` — because a cycle posts in
    the month before the one it bills (September propinas posted on 25 August).
    """
    if force:
        return False

    try:
        result = frappe.db.sql(
            """
            SELECT si.name
            FROM `tabSales Invoice` si
            WHERE si.escola_student = %s
              AND si.escola_is_addon_invoice = 1
              AND si.docstatus != 2
              AND YEAR(COALESCE(si.due_date, si.posting_date)) = YEAR(%s)
              AND MONTH(COALESCE(si.due_date, si.posting_date)) = MONTH(%s)
            LIMIT 1
            """,
            (student, ref_date, ref_date),
        )
        return bool(result)
    except Exception:
        return False


def _append_outcome_note(outcome, note):
    """Append a secondary note (e.g. an addon result) to an outcome's reason."""
    outcome["reason"] = (outcome["reason"] + " " + note).strip() if outcome["reason"] else note


def _write_generation_log(cycle, entries):
    """Replace the per-student generation log child table on the cycle.

    Runs before the db_set() summary block so the parent .save() here does not
    clobber those direct writes.
    """
    try:
        cycle.set("generation_log", [])
        for e in sorted(entries, key=lambda x: (x.get("status") != "Erro", x.get("student_name") or "")):
            cycle.append("generation_log", {
                "student": e["student"],
                "student_name": e.get("student_name"),
                "class_group": e.get("class_group"),
                "status": e.get("status") or "Ignorado",
                "reason": e.get("reason") or "",
                "sales_invoice": e.get("sales_invoice"),
            })
        cycle.save(ignore_permissions=True)
    except Exception:
        frappe.log_error(frappe.get_traceback(), _("Billing Cycle: falha ao gravar o detalhe por aluno"))


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
