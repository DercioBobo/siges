import calendar
from datetime import date, timedelta

import frappe
from frappe import _
from frappe.model.document import Document


class BillingSchedule(Document):
    def validate(self):
        day = int(self.invoice_day or 0)
        if day < 1 or day > 28:
            frappe.throw(_("O Dia de Emissão deve estar entre 1 e 28."))
        if self.billing_mode in ("Trimestral", "Anual") and not self.billing_month:
            frappe.throw(_("Defina o Mês de Referência para o modo {0}.").format(self.billing_mode))
        if self.billing_mode == "Trimestral" and not (1 <= int(self.billing_month or 0) <= 3):
            frappe.throw(_("Para Trimestral, o Mês de Referência deve ser 1, 2 ou 3."))
        if self.billing_mode == "Anual" and not (1 <= int(self.billing_month or 0) <= 12):
            frappe.throw(_("Para Anual, o Mês de Referência deve ser entre 1 e 12."))


# ---------------------------------------------------------------------------
# Scheduler entry point  (called daily via hooks.py)
# ---------------------------------------------------------------------------

def run_due_schedules():
    """Daily scheduler job — auto-generate invoices for due billing schedules."""
    today = date.today()
    schedules = frappe.get_all(
        "Billing Schedule",
        filters={"is_active": 1},
        fields=["name", "school_class", "billing_mode", "invoice_day",
                "due_days", "billing_month", "last_billed_date"],
    )
    for s in schedules:
        if not _is_due(s, today):
            continue
        try:
            _execute_schedule(s, today)
            frappe.db.set_value("Billing Schedule", s.name, "last_billed_date", today)
        except Exception:
            frappe.log_error(
                message=frappe.get_traceback(),
                title=_("Billing Schedule {0} falhou").format(s.name),
            )
    frappe.db.commit()


# ---------------------------------------------------------------------------
# Manual trigger
# ---------------------------------------------------------------------------

@frappe.whitelist()
def run_now(schedule_name):
    """Manually execute a billing schedule immediately."""
    s = frappe.get_doc("Billing Schedule", schedule_name)
    if not s.is_active:
        frappe.throw(_("Este agendamento está inactivo."))
    today = date.today()
    result = _execute_schedule(s, today)
    frappe.db.set_value("Billing Schedule", s.name, "last_billed_date", today)
    frappe.db.commit()
    return result


# ---------------------------------------------------------------------------
# Schedule info  (for form dashboard card)
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_schedule_info(schedule_name):
    s = frappe.get_doc("Billing Schedule", schedule_name)
    next_date = _next_trigger_date(s)
    student_count = frappe.db.count(
        "Student Group Assignment",
        {"school_class": s.school_class, "status": "Activa"},
    )
    fs_name = frappe.db.get_value(
        "Fee Structure",
        {"school_class": s.school_class, "is_active": 1},
        "name",
    )
    expected_per_student = 0.0
    if fs_name:
        lines = frappe.get_all(
            "Fee Structure Line",
            filters={"parent": fs_name, "billing_mode": s.billing_mode},
            fields=["amount"],
        )
        expected_per_student = sum(float(ln.amount or 0) for ln in lines)

    return {
        "next_due_date":        str(next_date) if next_date else None,
        "student_count":        student_count,
        "expected_per_student": expected_per_student,
        "expected_total":       expected_per_student * student_count,
    }


# ---------------------------------------------------------------------------
# Core logic helpers
# ---------------------------------------------------------------------------

def _settings_invoice_day():
    return int(frappe.db.get_single_value("School Settings", "invoice_posting_day") or 25)


def _settings_due_days():
    return int(frappe.db.get_single_value("School Settings", "invoice_due_days") or 15)


def _is_due(schedule, today):
    """Return True if this schedule should fire today."""
    day = int(schedule.invoice_day or 0) or _settings_invoice_day()
    if today.day < day:
        return False

    last = frappe.utils.getdate(schedule.last_billed_date) if schedule.last_billed_date else None
    mode = schedule.billing_mode

    if mode == "Mensal":
        if last and last.year == today.year and last.month == today.month:
            return False
        return True

    elif mode == "Trimestral":
        start = int(schedule.billing_month or 1)
        trigger_months = {((start - 1 + i * 3) % 12) + 1 for i in range(4)}
        if today.month not in trigger_months:
            return False
        if last:
            def _q(d): return (d.month - 1) // 3
            if last.year == today.year and _q(last) == _q(today):
                return False
        return True

    elif mode == "Anual":
        bm = int(schedule.billing_month or 1)
        if today.month != bm:
            return False
        if last and last.year == today.year:
            return False
        return True

    return False


def _next_trigger_date(schedule):
    """Compute the next calendar date this schedule will fire."""
    today = date.today()
    day   = min(int(schedule.invoice_day or 25), 28)
    mode  = schedule.billing_mode

    day = min(int(schedule.invoice_day or 0) or _settings_invoice_day(), 28)

    if mode == "Mensal":
        for delta in range(14):
            year  = today.year + ((today.month - 1 + delta) // 12)
            month = ((today.month - 1 + delta) % 12) + 1
            safe  = min(day, calendar.monthrange(year, month)[1])
            c = date(year, month, safe)
            if c > today:
                return c

    elif mode == "Trimestral":
        start = int(schedule.billing_month or 1)
        trigger_months = sorted([((start - 1 + i * 3) % 12) + 1 for i in range(4)])
        for yr_delta in range(3):
            year = today.year + yr_delta
            for m in trigger_months:
                safe = min(day, calendar.monthrange(year, m)[1])
                c = date(year, m, safe)
                if c > today:
                    return c

    elif mode == "Anual":
        bm = int(schedule.billing_month or 1)
        for yr_delta in range(3):
            year = today.year + yr_delta
            safe = min(day, calendar.monthrange(year, bm)[1])
            c = date(year, bm, safe)
            if c > today:
                return c

    return None


def _execute_schedule(schedule, today_date):
    """Create a Billing Cycle and generate invoices for this schedule."""
    from escola.escola.doctype.billing_cycle.billing_cycle import generate_invoices

    due_date      = today_date + timedelta(days=int(schedule.due_days or 0) or _settings_due_days())
    academic_year = frappe.db.get_single_value("School Settings", "current_academic_year")
    month_label   = today_date.strftime("%m/%Y")
    cycle_name    = f"{schedule.school_class} · {schedule.billing_mode} · {month_label}"

    # Guard against double execution for the same period
    if frappe.db.exists("Billing Cycle", {"cycle_name": cycle_name}):
        return {"skipped": True, "reason": "already_exists"}

    cycle = frappe.get_doc({
        "doctype":          "Billing Cycle",
        "cycle_name":       cycle_name,
        "academic_year":    academic_year,
        "school_class":     schedule.school_class,
        "billing_mode":     schedule.billing_mode,
        "posting_date":     today_date,
        "due_date":         due_date,
        "billing_schedule": schedule.name,
        "status":           "Rascunho",
    })
    cycle.insert(ignore_permissions=True)
    return generate_invoices(cycle.name)
