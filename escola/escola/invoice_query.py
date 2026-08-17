"""
Shared invoice filter/query logic used by both the "Monitor de Facturas"
(invoice_monitor) and "Central de Pagamentos" (payment_desk) pages, so the
Estado/status rules only need to be correct in one place.
"""

import json

import frappe
from frappe.utils import getdate, today

ALL_STATUSES = ("Em Aberto", "Paga", "Em Dívida", "Vencida")


@frappe.whitelist()
def get_filter_options():
    """Dropdown data for Classe and Turma filters."""
    classes = frappe.get_all(
        "School Class", filters={"is_active": 1},
        fields=["name", "class_name"], order_by="class_level asc",
    )
    turmas = frappe.get_all(
        "Class Group", filters={"is_active": 1},
        fields=["name", "group_name", "school_class"], order_by="group_name asc",
    )
    return {"classes": classes, "turmas": turmas}


def _normalize_statuses(status):
    """Accept a real list, a JSON-encoded list, a comma-separated string, or None."""
    if not status:
        return []
    if isinstance(status, (list, tuple)):
        values = list(status)
    elif isinstance(status, str):
        s = status.strip()
        if s.startswith("["):
            try:
                values = json.loads(s)
            except ValueError:
                values = [s]
        else:
            values = [v.strip() for v in s.split(",") if v.strip()]
    else:
        values = [status]

    seen = []
    for v in values:
        if v in ALL_STATUSES and v not in seen:
            seen.append(v)
    return seen


def _status_sql(statuses, today_val, params):
    """
    Build one OR-grouped SQL fragment for the selected Estado values.

    "Em Aberto" is its own top-level branch (docstatus = 0). The other three
    are each scoped to docstatus = 1 inside a single shared wrapper — this is
    what fixes a draft invoice (outstanding_amount typically 0/unset before
    submission) from being miscategorized as "Paga".
    """
    if not statuses:
        return ""

    branches = []
    if "Em Aberto" in statuses:
        branches.append("si.docstatus = 0")

    submitted_conditions = []
    if "Paga" in statuses:
        submitted_conditions.append("si.outstanding_amount <= 0")
    if "Em Dívida" in statuses:
        params["today_ed"] = today_val
        submitted_conditions.append("(si.outstanding_amount > 0 AND si.due_date >= %(today_ed)s)")
    if "Vencida" in statuses:
        params["today_v"] = today_val
        submitted_conditions.append("(si.outstanding_amount > 0 AND si.due_date < %(today_v)s)")
    if submitted_conditions:
        branches.append("(si.docstatus = 1 AND (" + " OR ".join(submitted_conditions) + "))")

    return "(" + " OR ".join(branches) + ")" if branches else ""


@frappe.whitelist()
def get_invoices(from_date=None, to_date=None, school_class=None,
                  class_group=None, student=None, status=None):
    """Return filtered invoice rows and summary stats."""
    conditions = ["si.docstatus != 2", "si.escola_billing_cycle IS NOT NULL"]
    params = {}

    if from_date:
        conditions.append("si.posting_date >= %(from_date)s")
        params["from_date"] = from_date
    if to_date:
        conditions.append("si.posting_date <= %(to_date)s")
        params["to_date"] = to_date
    if school_class:
        conditions.append("bc.school_class = %(school_class)s")
        params["school_class"] = school_class
    if class_group:
        conditions.append("sga.class_group = %(class_group)s")
        params["class_group"] = class_group
    if student:
        conditions.append(
            "(si.escola_student LIKE %(student)s OR st.full_name LIKE %(student)s)"
        )
        params["student"] = f"%{student}%"

    today_val = today()
    status_sql = _status_sql(_normalize_statuses(status), today_val, params)
    if status_sql:
        conditions.append(status_sql)

    where = " AND ".join(conditions)

    rows = frappe.db.sql(f"""
        SELECT
            si.name               AS invoice,
            si.docstatus,
            si.escola_student     AS student,
            st.full_name          AS student_name,
            bc.school_class,
            sga.class_group,
            cg.group_name         AS turma_name,
            si.posting_date,
            si.due_date,
            si.grand_total,
            si.outstanding_amount,
            bc.billing_mode,
            (
                SELECT COALESCE(SUM(sii.amount), 0) FROM `tabSales Invoice Item` sii
                WHERE sii.parent = si.name AND sii.escola_is_penalty_line = 1
            ) AS penalty_amount
        FROM `tabSales Invoice` si
        LEFT JOIN `tabBilling Cycle` bc
               ON bc.name = si.escola_billing_cycle
        LEFT JOIN `tabStudent` st
               ON st.name = si.escola_student
        LEFT JOIN `tabStudent Group Assignment` sga
               ON sga.student    = si.escola_student
              AND sga.school_class = bc.school_class
              AND sga.status     = 'Activa'
        LEFT JOIN `tabClass Group` cg
               ON cg.name = sga.class_group
        WHERE {where}
        GROUP BY si.name
        ORDER BY si.posting_date DESC
        LIMIT 1000
    """, params, as_dict=True)

    today_date = getdate(today_val)
    for r in rows:
        paid = float(r.grand_total or 0) - float(r.outstanding_amount or 0)
        r.paid = round(paid, 2)
        if r.docstatus == 0:
            r.display_status = "Em Aberto"
        elif float(r.outstanding_amount or 0) <= 0:
            r.display_status = "Paga"
        elif getdate(r.due_date) < today_date:
            r.display_status = "Vencida"
        else:
            r.display_status = "Em Dívida"

    total_invoiced    = sum(float(r.grand_total or 0) for r in rows)
    total_paid        = sum(r.paid for r in rows)
    total_outstanding = sum(float(r.outstanding_amount or 0) for r in rows)
    total_overdue     = sum(
        float(r.outstanding_amount or 0) for r in rows if r.display_status == "Vencida"
    )

    return {
        "rows": rows,
        "summary": {
            "count":             len(rows),
            "total_invoiced":    round(total_invoiced, 2),
            "total_paid":        round(total_paid, 2),
            "total_outstanding": round(total_outstanding, 2),
            "total_overdue":     round(total_overdue, 2),
        },
    }
