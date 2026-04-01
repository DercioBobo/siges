"""
escola/escola/doctype/billing_cycle/penalty.py

Penalty calculation engine for the Escola billing module.
All public functions are callable on-demand — no scheduled jobs.
"""

import math

import frappe
from frappe import _
from frappe.utils import date_diff, getdate, today


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

def _get_settings():
    s = frappe.get_single("School Settings")
    return {
        "penalty_grace_days":          int(s.penalty_grace_days or 0),
        "penalty_increment_percent":   float(s.penalty_increment_percent or 10.0),
        "penalty_max_percent":         float(s.penalty_max_percent or 30.0),
        "penalty_frequency":           s.penalty_frequency or "Semanal",
        "penalty_mode":                s.penalty_mode or "Dinâmico",
        "penalty_item_code":           s.penalty_item_code or "Multa por Atraso",
        "auto_suspend_on_non_payment": int(s.auto_suspend_on_non_payment or 0),
        "suspension_threshold_weeks":  int(s.suspension_threshold_weeks or 4),
        "auto_submit_on_suspension":   int(s.auto_submit_on_suspension or 0),
    }


def _frequency_days(frequency):
    return {"Semanal": 7, "Quinzenal": 14, "Mensal": 30}.get(frequency, 7)


def _frequency_label(frequency, periods):
    if frequency == "Semanal":
        unit = "semana" if periods == 1 else "semanas"
    elif frequency == "Quinzenal":
        unit = "quinzena" if periods == 1 else "quinzenas"
    else:
        unit = "mês" if periods == 1 else "meses"
    return f"{periods} {unit} de atraso"


# ---------------------------------------------------------------------------
# Core calculation (pure, no side effects)
# ---------------------------------------------------------------------------

def _compute_penalty(due_date, settings):
    """
    Compute penalty data for a due_date against today.
    Returns dict: days_overdue, periods, penalty_rate, penalty_amount_factor.
    penalty_amount_factor is a decimal fraction (e.g. 0.20 for 20%).
    """
    if not due_date:
        return {"days_overdue": 0, "periods": 0, "penalty_rate": 0.0, "penalty_amount_factor": 0.0}

    grace      = settings["penalty_grace_days"]
    freq_days  = _frequency_days(settings["penalty_frequency"])
    increment  = settings["penalty_increment_percent"]
    max_pct    = settings["penalty_max_percent"]

    raw_overdue = date_diff(today(), getdate(due_date))
    effective   = raw_overdue - grace

    if effective <= 0:
        return {"days_overdue": max(0, raw_overdue), "periods": 0, "penalty_rate": 0.0, "penalty_amount_factor": 0.0}

    periods = math.ceil(effective / freq_days)
    rate    = min(periods * increment, max_pct)

    return {
        "days_overdue":          raw_overdue,
        "periods":               periods,
        "penalty_rate":          round(rate, 4),
        "penalty_amount_factor": round(rate / 100.0, 6),
    }


def _financial_status_from_periods(periods, settings):
    threshold = settings["suspension_threshold_weeks"]
    if periods == 0:
        return "Regular"
    if periods >= threshold:
        return "Suspenso" if settings["auto_suspend_on_non_payment"] else "Em Dívida Crítica"
    if periods >= 3:
        return "Em Dívida Crítica"
    return "Em Dívida"


def _alert_level(periods, settings):
    threshold = settings["suspension_threshold_weeks"]
    if periods >= threshold:
        return 4  # Elegível para suspensão
    if periods >= 3:
        return 3  # Risco de suspensão
    if periods >= 2:
        return 2  # Multa significativa
    if periods >= 1:
        return 1  # Pagamento em atraso
    return 0


# ---------------------------------------------------------------------------
# Invoice helpers
# ---------------------------------------------------------------------------

def _get_base_total(invoice_name):
    """Sum of non-penalty item amounts on an invoice."""
    try:
        items = frappe.get_all(
            "Sales Invoice Item",
            filters={"parent": invoice_name},
            fields=["amount", "escola_is_penalty_line"],
        )
        return sum((i.amount or 0.0) for i in items if not i.get("escola_is_penalty_line"))
    except Exception:
        return float(frappe.db.get_value("Sales Invoice", invoice_name, "grand_total") or 0)


def _remove_penalty_lines(inv):
    """Remove all penalty lines from a Sales Invoice doc in memory."""
    inv.items = [row for row in inv.items if not row.get("escola_is_penalty_line")]


def _get_or_create_penalty_item(item_code=None):
    """Return the item_code for penalty lines, creating the ERPNext Item if absent."""
    if not item_code:
        item_code = "Multa por Atraso"
    if frappe.db.exists("Item", item_code):
        return item_code

    groups = frappe.get_all("Item Group", filters={"is_group": 0}, fields=["name"], limit=1)
    item_group = groups[0].name if groups else "All Item Groups"

    frappe.get_doc({
        "doctype": "Item",
        "item_code": item_code,
        "item_name": item_code,
        "item_group": item_group,
        "is_stock_item": 0,
        "include_item_in_manufacturing": 0,
        "description": "Multa por atraso no pagamento de propinas escolares.",
    }).insert(ignore_permissions=True)
    frappe.db.commit()
    return item_code


def _apply_suspension(invoice_name, penalty_data, settings):
    """
    At suspension threshold: update student financial_status
    and optionally auto-submit the invoice.
    """
    threshold = settings["suspension_threshold_weeks"]
    if penalty_data["periods"] < threshold:
        return

    student = frappe.db.get_value("Sales Invoice", invoice_name, "escola_student")
    if student:
        status = "Suspenso" if settings["auto_suspend_on_non_payment"] else "Em Dívida Crítica"
        frappe.db.set_value("Student", student, "financial_status", status, update_modified=False)

    if settings["auto_submit_on_suspension"]:
        if frappe.db.get_value("Sales Invoice", invoice_name, "docstatus") == 0:
            frappe.get_doc("Sales Invoice", invoice_name).submit()


# ---------------------------------------------------------------------------
# Public whitelisted API
# ---------------------------------------------------------------------------

@frappe.whitelist()
def calculate_penalty(invoice_name):
    """
    Calculate penalty for a Sales Invoice without modifying anything.
    Safe to call at any time — purely informational.
    """
    inv = frappe.db.get_value(
        "Sales Invoice", invoice_name,
        ["due_date", "grand_total", "outstanding_amount", "docstatus", "escola_student"],
        as_dict=True,
    )
    if not inv:
        frappe.throw(_("Factura não encontrada: {0}").format(invoice_name))

    settings = _get_settings()
    pd        = _compute_penalty(inv.due_date, settings)
    base      = _get_base_total(invoice_name)
    penalty   = round(base * pd["penalty_amount_factor"], 2)

    return {
        "invoice":            invoice_name,
        "due_date":           str(inv.due_date) if inv.due_date else None,
        "days_overdue":       pd["days_overdue"],
        "periods":            pd["periods"],
        "penalty_rate":       pd["penalty_rate"],
        "base_total":         base,
        "penalty_amount":     penalty,
        "total_with_penalty": round(base + penalty, 2),
        "outstanding_amount": inv.outstanding_amount or 0,
        "docstatus":          inv.docstatus,
        "financial_status":   _financial_status_from_periods(pd["periods"], settings),
        "alert_level":        _alert_level(pd["periods"], settings),
    }


@frappe.whitelist()
def apply_penalty_to_invoice(invoice_name):
    """
    Add or update the penalty line on a DRAFT Sales Invoice.
    Idempotent: removes any existing penalty line before adding the updated one.
    Only operates when penalty_mode == "Adicionar à Factura" and docstatus == 0.
    """
    settings = _get_settings()

    if settings["penalty_mode"] != "Adicionar à Factura":
        return {"skipped": True, "reason": "penalty_mode_is_dynamic"}

    inv = frappe.get_doc("Sales Invoice", invoice_name)

    if inv.docstatus != 0:
        frappe.throw(
            _("Só é possível aplicar multas a facturas em Rascunho. "
              "Estado actual: <b>{0}</b>.").format(inv.docstatus),
            title=_("Factura não editável"),
        )

    pd = _compute_penalty(inv.due_date, settings)

    # Always remove old penalty lines first (keeps the operation idempotent)
    _remove_penalty_lines(inv)

    if pd["penalty_rate"] <= 0:
        inv.save(ignore_permissions=True)
        return {"applied": False, "reason": "not_overdue"}

    # base_total after removal — recalculate from the in-memory items list
    base_total = sum((row.amount or 0.0) for row in inv.items)
    penalty_amount = round(base_total * pd["penalty_amount_factor"], 2)

    if penalty_amount <= 0:
        inv.save(ignore_permissions=True)
        return {"applied": False, "reason": "zero_penalty"}

    penalty_item = _get_or_create_penalty_item(settings["penalty_item_code"])
    label = _frequency_label(settings["penalty_frequency"], pd["periods"])

    new_row = inv.append("items", {
        "item_code":  penalty_item,
        "item_name":  f"Multa por Atraso \u2013 {label}",
        "description": f"Multa por atraso de pagamento: {pd['penalty_rate']}% ({label})",
        "qty":        1,
        "rate":       penalty_amount,
    })
    new_row.escola_is_penalty_line = 1

    inv.save(ignore_permissions=True)

    _apply_suspension(invoice_name, pd, settings)

    return {
        "applied":        True,
        "periods":        pd["periods"],
        "penalty_rate":   pd["penalty_rate"],
        "penalty_amount": penalty_amount,
    }


@frappe.whitelist()
def apply_penalties_for_cycle(billing_cycle_name):
    """
    Apply penalties to all draft invoices in a Billing Cycle.
    Returns summary counts. Idempotent.
    """
    try:
        invoices = frappe.get_all(
            "Sales Invoice",
            filters={"escola_billing_cycle": billing_cycle_name, "docstatus": 0},
            fields=["name"],
        )
    except Exception:
        invoices = []

    applied, skipped, errors = 0, 0, []

    for inv in invoices:
        try:
            result = apply_penalty_to_invoice(inv.name)
            if result.get("applied"):
                applied += 1
            else:
                skipped += 1
        except Exception as e:
            errors.append({"invoice": inv.name, "error": str(e)})

    frappe.db.commit()
    return {"applied": applied, "skipped": skipped, "errors": errors}


@frappe.whitelist()
def update_student_financial_status(student_name):
    """
    Recalculate and persist financial_status on a Student record.
    Uses the worst (most overdue) outstanding invoice to determine status.
    """
    settings = _get_settings()

    try:
        invoices = frappe.get_all(
            "Sales Invoice",
            filters=[["escola_student", "=", student_name], ["docstatus", "!=", 2]],
            fields=["due_date", "grand_total", "outstanding_amount", "docstatus"],
        )
    except Exception:
        invoices = []

    worst_periods = 0
    for inv in invoices:
        if not inv.due_date:
            continue
        owed = inv.outstanding_amount if inv.docstatus == 1 else (inv.grand_total or 0)
        if not owed or owed <= 0:
            continue
        pd = _compute_penalty(inv.due_date, settings)
        if pd["periods"] > worst_periods:
            worst_periods = pd["periods"]

    status = _financial_status_from_periods(worst_periods, settings)
    frappe.db.set_value("Student", student_name, "financial_status", status, update_modified=False)
    frappe.db.commit()
    return {"student": student_name, "financial_status": status}


@frappe.whitelist()
def get_student_financial_summary(student_name):
    """
    Return financial summary for display on the Student form.
    Read-only — does NOT modify any data.
    """
    settings = _get_settings()

    try:
        all_invoices = frappe.get_all(
            "Sales Invoice",
            filters=[["escola_student", "=", student_name], ["docstatus", "!=", 2]],
            fields=["name", "due_date", "grand_total", "outstanding_amount", "docstatus"],
        )
    except Exception:
        all_invoices = []

    owed_invoices = []
    for inv in all_invoices:
        owed = float(inv.outstanding_amount or 0) if inv.docstatus == 1 else float(inv.grand_total or 0)
        if owed > 0:
            inv["_owed"] = owed
            owed_invoices.append(inv)

    if not owed_invoices:
        return {
            "student":           student_name,
            "total_outstanding": 0.0,
            "invoice_count":     0,
            "worst_invoice":     None,
            "days_overdue":      0,
            "periods":           0,
            "penalty_rate":      0.0,
            "penalty_amount":    0.0,
            "total_with_penalty": 0.0,
            "financial_status":  frappe.db.get_value("Student", student_name, "financial_status") or "Regular",
            "alert_level":       0,
            "penalty_frequency": settings["penalty_frequency"],
        }

    total_outstanding = sum(i["_owed"] for i in owed_invoices)

    # Find worst (most overdue) invoice
    worst_inv  = None
    worst_pd   = None
    for inv in owed_invoices:
        pd = _compute_penalty(inv.due_date, settings)
        if worst_pd is None or pd["periods"] > worst_pd["periods"]:
            worst_inv = inv
            worst_pd  = pd

    base_worst     = _get_base_total(worst_inv.name)
    penalty_amount = round(base_worst * worst_pd["penalty_amount_factor"], 2)

    return {
        "student":           student_name,
        "total_outstanding": total_outstanding,
        "invoice_count":     len(owed_invoices),
        "worst_invoice":     worst_inv.name,
        "days_overdue":      worst_pd["days_overdue"],
        "periods":           worst_pd["periods"],
        "penalty_rate":      worst_pd["penalty_rate"],
        "penalty_amount":    penalty_amount,
        "total_with_penalty": round(total_outstanding + penalty_amount, 2),
        "financial_status":  _financial_status_from_periods(worst_pd["periods"], settings),
        "alert_level":       _alert_level(worst_pd["periods"], settings),
        "penalty_frequency": settings["penalty_frequency"],
    }


# ---------------------------------------------------------------------------
# Automatic triggers (hooks)
# ---------------------------------------------------------------------------

def on_sales_invoice_update(doc, method):
    """
    Called automatically when a Sales Invoice is updated after submit or cancelled.
    Recalculates financial_status for the linked student.
    """
    student = getattr(doc, "escola_student", None)
    if not student:
        try:
            student = frappe.db.get_value("Sales Invoice", doc.name, "escola_student")
        except Exception:
            return
    if student:
        try:
            update_student_financial_status(student)
        except Exception:
            pass


def apply_all_pending_penalties():
    """
    Daily scheduled job — only runs when penalty_mode == "Adicionar à Factura".
    Finds every overdue draft invoice and applies/updates its penalty line.
    Safe to run daily: apply_penalty_to_invoice is idempotent and only changes
    the amount when a new penalty period is crossed.
    """
    settings = _get_settings()
    if settings["penalty_mode"] != "Adicionar à Factura":
        return

    try:
        invoices = frappe.db.sql(
            """
            SELECT name
            FROM `tabSales Invoice`
            WHERE docstatus = 0
              AND outstanding_amount > 0
              AND due_date < CURDATE()
              AND escola_billing_cycle IS NOT NULL
              AND escola_billing_cycle != ''
            """,
            as_dict=True,
        )
    except Exception:
        return

    for inv in invoices:
        try:
            apply_penalty_to_invoice(inv.name)
        except Exception:
            frappe.log_error(
                title="Escola — erro ao aplicar multa automática",
                message=frappe.get_traceback(),
            )

    if invoices:
        frappe.db.commit()


def update_all_student_financial_statuses():
    """
    Daily scheduled job: recalculate financial_status for every student
    who has at least one non-cancelled invoice.
    Catches time-based transitions (due dates crossed overnight).
    """
    try:
        rows = frappe.db.sql(
            """
            SELECT DISTINCT escola_student
            FROM `tabSales Invoice`
            WHERE docstatus != 2
              AND escola_student IS NOT NULL
              AND escola_student != ''
            """,
            as_dict=True,
        )
    except Exception:
        return

    for row in rows:
        try:
            update_student_financial_status(row.escola_student)
        except Exception:
            frappe.log_error(
                title="Escola — erro ao actualizar estado financeiro",
                message=frappe.get_traceback(),
            )
