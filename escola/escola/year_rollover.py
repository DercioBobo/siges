"""
escola/year_rollover.py

Watches the current Academic Year's end date and reminds management to
prepare the next year. One status function feeds two surfaces:

- get_rollover_status()  → desk banner (escola_utils.js) with a live checklist
- daily_reminder()       → scheduler: bell notification for Diretor/Secretaria,
                           throttled to once per cooldown window
"""
import frappe
from frappe import _
from frappe.utils import add_days, cint, date_diff, today

BANNER_ROLES = {"System Manager", "Diretor Escolar", "Secretaria Escolar"}
NOTIFY_ROLES = ("Diretor Escolar", "Secretaria Escolar")
DEFAULT_REMINDER_DAYS = 60
NOTIFICATION_SUBJECT = "Preparação do novo ano lectivo"
NOTIFICATION_COOLDOWN_DAYS = 7


def _compute_status():
    settings = frappe.get_single("School Settings")
    current = settings.current_academic_year
    if not current:
        return None

    year = frappe.db.get_value(
        "Academic Year", current, ["name", "start_date", "end_date"], as_dict=True
    )
    if not year or not year.end_date:
        return None

    days_left = date_diff(year.end_date, today())
    threshold = cint(settings.get("rollover_reminder_days")) or DEFAULT_REMINDER_DAYS

    # "Next year" = the earliest Academic Year starting after the current one —
    # independent of naming conventions like "2026" vs "2025/2026".
    next_year = frappe.db.get_value(
        "Academic Year",
        {"start_date": (">", year.start_date), "name": ("!=", year.name)},
        "name",
        order_by="start_date asc",
    )

    has_terms = bool(
        next_year and frappe.db.count("Academic Term", {"academic_year": next_year})
    )
    has_turmas = bool(
        next_year
        and frappe.db.count("Class Group", {"academic_year": next_year, "is_active": 1})
    )
    abertura_done = bool(
        next_year
        and frappe.db.get_value(
            "Abertura de Ano Lectivo",
            {"target_academic_year": next_year, "docstatus": 1},
            "name",
        )
    )

    steps = [
        {"key": "year", "label": _("Criar o novo Ano Lectivo"), "done": bool(next_year)},
        {"key": "terms", "label": _("Criar os trimestres do novo ano"), "done": has_terms},
        {"key": "turmas", "label": _("Criar turmas / correr as promoções"), "done": has_turmas},
        {"key": "abertura", "label": _("Submeter a Abertura de Ano Lectivo"), "done": abertura_done},
    ]

    return {
        "current_year": year.name,
        "end_date": str(year.end_date),
        "days_left": days_left,
        "threshold": threshold,
        "next_year": next_year,
        "steps": steps,
        "needs_action": days_left <= threshold and any(not s["done"] for s in steps),
    }


@frappe.whitelist()
def get_rollover_status():
    if not BANNER_ROLES & set(frappe.get_roles()):
        return {}
    return _compute_status() or {}


def _headline(status):
    if status["days_left"] >= 0:
        return _("O ano lectivo {0} termina em {1} dia(s).").format(
            status["current_year"], status["days_left"]
        )
    return _("O ano lectivo {0} terminou há {1} dia(s).").format(
        status["current_year"], -status["days_left"]
    )


def notify_management(subject, content, subject_prefix=None,
                      cooldown_days=NOTIFICATION_COOLDOWN_DAYS):
    """Bell-notify every Diretor/Secretaria user, throttled per subject prefix.

    `subject_prefix` groups related reminders for throttling (the variable part
    of the subject — e.g. a day count — would otherwise defeat the cooldown).
    """
    prefix = subject_prefix or subject
    cutoff = add_days(today(), -cooldown_days)
    if frappe.db.exists(
        "Notification Log",
        {"subject": ("like", prefix + "%"), "creation": (">=", cutoff)},
    ):
        return

    users = frappe.db.sql_list(
        """
        SELECT DISTINCT hr.parent
        FROM `tabHas Role` hr
        JOIN `tabUser` u ON u.name = hr.parent
        WHERE hr.role IN %(roles)s
          AND u.enabled = 1
          AND u.name NOT IN ('Administrator', 'Guest')
        """,
        {"roles": NOTIFY_ROLES},
    )

    for user in users:
        frappe.get_doc({
            "doctype": "Notification Log",
            "for_user": user,
            "type": "Alert",
            "subject": subject,
            "email_content": content,
        }).insert(ignore_permissions=True)


def daily_reminder():
    """Scheduler (daily): notify management while the year rollover is pending."""
    status = _compute_status()
    if not status or not status["needs_action"]:
        return

    pending = ", ".join(s["label"] for s in status["steps"] if not s["done"])
    notify_management(
        subject=f"{NOTIFICATION_SUBJECT}: {_headline(status)}",
        content=_("Passos pendentes: {0}.").format(pending),
        subject_prefix=NOTIFICATION_SUBJECT,
    )
