from datetime import date, timedelta
import frappe
from frappe import _


@frappe.whitelist()
def get_schedule_data():
    """All billing schedules enriched with next due dates and expected amounts."""
    from escola.escola.doctype.billing_schedule.billing_schedule import (
        _next_trigger_date,
        _is_due,
    )

    schedules = frappe.get_all(
        "Billing Schedule",
        fields=["name", "schedule_name", "school_class", "billing_mode",
                "invoice_day", "due_days", "billing_month",
                "is_active", "last_billed_date"],
        order_by="school_class asc, billing_mode asc",
    )

    today = date.today()
    result = []

    for s in schedules:
        try:
            next_date = _next_trigger_date(s)
            overdue   = _is_due(s, today)
        except Exception:
            next_date = None
            overdue   = False

        try:
            student_count = frappe.db.count(
                "Student",
                {"current_school_class": s.school_class, "current_status": "Activo"},
            )
        except Exception:
            student_count = 0

        expected_per = 0.0
        try:
            fs_name = frappe.db.get_value(
                "Fee Structure",
                {"school_class": s.school_class, "is_active": 1},
                "name",
            )
            if fs_name:
                lines = frappe.get_all(
                    "Fee Structure Line",
                    filters={"parent": fs_name, "billing_mode": s.billing_mode},
                    fields=["amount"],
                )
                expected_per = sum(float(ln.amount or 0) for ln in lines)
        except Exception:
            pass

        result.append({
            "name":            s.name,
            "schedule_name":   s.schedule_name,
            "school_class":    s.school_class,
            "billing_mode":    s.billing_mode,
            "invoice_day":     s.invoice_day,
            "is_active":       s.is_active,
            "last_billed_date":str(s.last_billed_date) if s.last_billed_date else None,
            "next_due_date":   str(next_date) if next_date else None,
            "is_overdue":      overdue,
            "student_count":   student_count,
            "expected_per":    expected_per,
            "expected_total":  expected_per * student_count,
        })

    # Upcoming timeline — next 30 days
    cutoff = str(today + timedelta(days=30))
    timeline_map = {}
    for s in result:
        d = s.get("next_due_date")
        if not d or d > cutoff:
            continue
        if d not in timeline_map:
            timeline_map[d] = []
        timeline_map[d].append({
            "name":           s["name"],
            "schedule_name":  s["schedule_name"],
            "school_class":   s["school_class"],
            "student_count":  s["student_count"],
            "expected_total": s["expected_total"],
        })

    upcoming = [
        {"date": d, "entries": entries}
        for d, entries in sorted(timeline_map.items())
    ]

    return {"schedules": result, "upcoming": upcoming}
