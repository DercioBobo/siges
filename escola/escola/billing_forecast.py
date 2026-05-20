"""
escola/billing_forecast.py

On-the-fly billing forecast for a student.
Generates all expected billing periods within the current academic year
based on the active Billing Schedule(s) and Fee Structure for the student's class,
then overlays actual invoice status (Previsto / Rascunho / Facturado / Pago).
"""
import calendar
from datetime import date, timedelta

import frappe
from frappe import _
from frappe.utils import getdate


# ---------------------------------------------------------------------------
# Due-date helpers (mirror billing_schedule.py to avoid cross-import)
# ---------------------------------------------------------------------------

def _next_due_day(posting_date, day):
    max_same = calendar.monthrange(posting_date.year, posting_date.month)[1]
    candidate = posting_date.replace(day=min(day, max_same))
    if candidate > posting_date:
        due = candidate
    else:
        if posting_date.month == 12:
            y, m = posting_date.year + 1, 1
        else:
            y, m = posting_date.year, posting_date.month + 1
        due = date(y, m, min(day, calendar.monthrange(y, m)[1]))
    if due.weekday() == 5:
        due += timedelta(days=2)
    elif due.weekday() == 6:
        due += timedelta(days=1)
    return due


def _compute_due_date(posting_date, due_days):
    """Return due date for posting_date, respecting payment_due_day and active exceptions."""
    from escola.escola.doctype.payment_exception.payment_exception import get_active_exception

    payment_due_day = int(frappe.db.get_single_value("School Settings", "payment_due_day") or 0)
    if payment_due_day:
        due_date = _next_due_day(posting_date, payment_due_day)
    else:
        due_date = posting_date + timedelta(days=due_days)

    exception = get_active_exception(posting_date)
    if exception and exception.extended_due_date:
        due_date = getdate(exception.extended_due_date)

    return due_date


# ---------------------------------------------------------------------------
# Period generation
# ---------------------------------------------------------------------------

def _billing_periods(sched, ay_start, ay_end, invoice_day):
    """Return list of {posting_date, period_label} for a schedule within [ay_start, ay_end]."""
    periods = []
    mode = sched.billing_mode
    billing_month = int(sched.billing_month or 1)

    if mode == "Mensal":
        cur = ay_start.replace(day=1)
        while cur <= ay_end:
            y, m = cur.year, cur.month
            safe = min(invoice_day, calendar.monthrange(y, m)[1])
            posting = date(y, m, safe)
            if ay_start <= posting <= ay_end:
                months_pt = [
                    "Janeiro","Fevereiro","Março","Abril","Maio","Junho",
                    "Julho","Agosto","Setembro","Outubro","Novembro","Dezembro",
                ]
                periods.append({
                    "posting_date": posting,
                    "period_label": f"{months_pt[m - 1]} {y}",
                })
            cur = date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)

    elif mode == "Trimestral":
        trigger_months = sorted([((billing_month - 1 + i * 3) % 12) + 1 for i in range(4)])
        for y in range(ay_start.year, ay_end.year + 1):
            for m in trigger_months:
                safe = min(invoice_day, calendar.monthrange(y, m)[1])
                posting = date(y, m, safe)
                if ay_start <= posting <= ay_end:
                    q = ((m - 1) // 3) + 1
                    periods.append({"posting_date": posting, "period_label": f"T{q}/{y}"})

    elif mode == "Anual":
        for y in range(ay_start.year, ay_end.year + 1):
            safe = min(invoice_day, calendar.monthrange(y, billing_month)[1])
            posting = date(y, billing_month, safe)
            if ay_start <= posting <= ay_end:
                periods.append({"posting_date": posting, "period_label": str(y)})

    return sorted(periods, key=lambda x: x["posting_date"])


# ---------------------------------------------------------------------------
# Invoice lookup
# ---------------------------------------------------------------------------

def _find_invoice(student_name, school_class, billing_mode, posting_date):
    """Return invoice row dict for this student+period, or None.
    Also checks advance payment (Adiantamento) coverage."""
    if billing_mode == "Mensal":
        period_sql = "YEAR(si.posting_date) = YEAR(%s) AND MONTH(si.posting_date) = MONTH(%s)"
        params = (student_name, school_class, billing_mode, posting_date, posting_date)
        adv_sql = "YEAR(apl.posting_date) = YEAR(%s) AND MONTH(apl.posting_date) = MONTH(%s)"
        adv_params = (student_name, billing_mode, posting_date, posting_date)
    elif billing_mode == "Trimestral":
        period_sql = "YEAR(si.posting_date) = YEAR(%s) AND QUARTER(si.posting_date) = QUARTER(%s)"
        params = (student_name, school_class, billing_mode, posting_date, posting_date)
        adv_sql = "YEAR(apl.posting_date) = YEAR(%s) AND QUARTER(apl.posting_date) = QUARTER(%s)"
        adv_params = (student_name, billing_mode, posting_date, posting_date)
    elif billing_mode == "Anual":
        period_sql = "YEAR(si.posting_date) = YEAR(%s)"
        params = (student_name, school_class, billing_mode, posting_date)
        adv_sql = "YEAR(apl.posting_date) = YEAR(%s)"
        adv_params = (student_name, billing_mode, posting_date)
    else:
        period_sql = "si.posting_date = %s"
        params = (student_name, school_class, billing_mode, posting_date)
        adv_sql = "apl.posting_date = %s"
        adv_params = (student_name, billing_mode, posting_date)

    rows = frappe.db.sql(f"""
        SELECT si.name, si.docstatus, si.grand_total, si.outstanding_amount, si.posting_date
        FROM `tabSales Invoice` si
        JOIN `tabBilling Cycle` bc ON bc.name = si.escola_billing_cycle
        WHERE si.escola_student = %s
          AND bc.school_class = %s
          AND bc.billing_mode = %s
          AND si.docstatus != 2
          AND {period_sql}
        ORDER BY si.posting_date DESC
        LIMIT 1
    """, params, as_dict=True)
    if rows:
        return rows[0]

    # Check advance payment coverage
    adv_rows = frappe.db.sql(f"""
        SELECT adp.name AS adiantamento_name, adp.sales_invoice,
               apl.gross_amount, adp.discount_percent
        FROM `tabAdiantamento Period Line` apl
        JOIN `tabAdiantamento De Pagamento` adp ON adp.name = apl.parent
        WHERE adp.student = %s
          AND adp.docstatus = 1
          AND apl.billing_mode = %s
          AND {adv_sql}
        ORDER BY adp.payment_date DESC
        LIMIT 1
    """, adv_params, as_dict=True)
    if adv_rows:
        a = adv_rows[0]
        period_net = float(a.gross_amount or 0) * (1 - float(a.discount_percent or 0) / 100)
        return frappe._dict({
            "name":             a.sales_invoice or a.adiantamento_name,
            "docstatus":        1,
            "grand_total":      period_net,
            "outstanding_amount": 0.0,
            "is_advance":       True,
            "adiantamento_name": a.adiantamento_name,
        })

    return None


def _period_status(inv):
    if not inv:
        return "Previsto"
    if inv.docstatus == 0:
        return "Rascunho"
    return "Pago" if float(inv.outstanding_amount or 0) <= 0 else "Facturado"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_student_forecast(student_name):
    """
    Compute billing forecast for a student.
    Returns {periods, academic_year, summary}.
    Each period: {period_label, posting_date, due_date, billing_mode, amount,
                  outstanding, status, invoice_name}.
    """
    student = frappe.db.get_value(
        "Student", student_name,
        ["current_class_group", "current_school_class"],
        as_dict=True,
    )
    if not student or not student.current_class_group:
        return {"periods": [], "academic_year": None, "summary": {}}

    school_class   = student.current_school_class
    class_group    = student.current_class_group
    ay_name        = frappe.db.get_value("Class Group", class_group, "academic_year")
    if not ay_name:
        return {"periods": [], "academic_year": None, "summary": {}}

    ay = frappe.db.get_value("Academic Year", ay_name, ["start_date", "end_date"], as_dict=True)
    if not ay or not ay.start_date or not ay.end_date:
        return {"periods": [], "academic_year": ay_name, "summary": {}}

    ay_start = getdate(ay.start_date)
    ay_end   = getdate(ay.end_date)

    schedules = frappe.get_all(
        "Billing Schedule",
        filters={"school_class": school_class, "is_active": 1},
        fields=["name", "billing_mode", "invoice_day", "due_days", "billing_month"],
    )
    if not schedules:
        return {"periods": [], "academic_year": ay_name, "summary": {}}

    fs_name = frappe.db.get_value(
        "Fee Structure",
        {"school_class": school_class, "is_active": 1},
        "name",
    )

    invoice_posting_day = int(frappe.db.get_single_value("School Settings", "invoice_posting_day") or 25)
    invoice_due_days    = int(frappe.db.get_single_value("School Settings", "invoice_due_days") or 15)

    all_periods = []
    for sched in schedules:
        invoice_day = int(sched.invoice_day or 0) or invoice_posting_day
        due_days    = int(sched.due_days or 0) or invoice_due_days

        fee_lines = frappe.get_all(
            "Fee Structure Line",
            filters={"parent": fs_name, "billing_mode": sched.billing_mode} if fs_name else {"name": ""},
            fields=["amount"],
        ) if fs_name else []
        base_amount = sum(float(ln.amount or 0) for ln in fee_lines)

        for p in _billing_periods(sched, ay_start, ay_end, invoice_day):
            posting_date = p["posting_date"]
            due_date     = _compute_due_date(posting_date, due_days)
            inv          = _find_invoice(student_name, school_class, sched.billing_mode, posting_date)
            status       = _period_status(inv)

            all_periods.append({
                "period_label":  p["period_label"],
                "posting_date":  str(posting_date),
                "due_date":      str(due_date),
                "billing_mode":  sched.billing_mode,
                "amount":        float(inv.grand_total or base_amount) if inv else base_amount,
                "outstanding":   float(inv.outstanding_amount or 0) if inv else 0.0,
                "status":        status,
                "invoice_name":  inv.name if inv else None,
                "is_advance":    bool(getattr(inv, "is_advance", False)) if inv else False,
                "adiantamento":  getattr(inv, "adiantamento_name", None) if inv else None,
            })

    all_periods.sort(key=lambda x: x["posting_date"])

    total_expected    = sum(p["amount"] for p in all_periods)
    total_paid        = sum(
        p["amount"] - p["outstanding"]
        for p in all_periods if p["status"] in ("Pago", "Facturado")
    )
    total_outstanding = sum(p["outstanding"] for p in all_periods if p["status"] in ("Facturado", "Rascunho"))
    total_previsto    = sum(p["amount"] for p in all_periods if p["status"] == "Previsto")

    return {
        "periods":      all_periods,
        "academic_year": ay_name,
        "summary": {
            "total_expected":    total_expected,
            "total_paid":        total_paid,
            "total_outstanding": total_outstanding,
            "total_previsto":    total_previsto,
            "count_previsto":    sum(1 for p in all_periods if p["status"] == "Previsto"),
            "count_rascunho":    sum(1 for p in all_periods if p["status"] == "Rascunho"),
            "count_facturado":   sum(1 for p in all_periods if p["status"] == "Facturado"),
            "count_pago":        sum(1 for p in all_periods if p["status"] == "Pago"),
        },
    }
