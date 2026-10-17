"""
Shared invoice filter/query logic used by both the "Monitor de Facturas"
(invoice_monitor) and "Central de Pagamentos" (payment_desk) pages, so the
Estado/status rules only need to be correct in one place.
"""

import json

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, getdate, today

from escola.escola.payment_actions import WAIVER_REMARK

ALL_STATUSES = ("Em Aberto", "Paga", "Em Dívida", "Vencida", "Parcialmente Paga")

# Multa still standing on an invoice: its multa lines minus what was waived.
# A draft's waiver deletes the line; a submitted invoice can't lose the line,
# so its waiver is a Journal Entry against the invoice — subtract those, or the
# multa keeps showing after it was waived. Needs params["waiver_like"].
_OPEN_PENALTY_SQL = """GREATEST(0,
    (SELECT COALESCE(SUM(sii.amount), 0) FROM `tabSales Invoice Item` sii
     WHERE sii.parent = si.name AND sii.escola_is_penalty_line = 1)
  - (SELECT COALESCE(SUM(jea.credit_in_account_currency), 0)
     FROM `tabJournal Entry Account` jea
     JOIN `tabJournal Entry` je ON je.name = jea.parent
     WHERE je.docstatus = 1 AND je.user_remark LIKE %(waiver_like)s
       AND jea.reference_type = 'Sales Invoice' AND jea.reference_name = si.name)
)"""


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
    if "Parcialmente Paga" in statuses:
        submitted_conditions.append("(si.outstanding_amount > 0 AND si.outstanding_amount < si.grand_total)")
    if submitted_conditions:
        branches.append("(si.docstatus = 1 AND (" + " OR ".join(submitted_conditions) + "))")

    return "(" + " OR ".join(branches) + ")" if branches else ""


@frappe.whitelist()
def get_invoices(from_date=None, to_date=None, school_class=None,
                  class_group=None, student=None, status=None, with_penalty=0):
    """Return filtered invoice rows and summary stats."""
    from escola.escola.doctype.billing_cycle.penalty import _compute_penalty, _get_settings

    settings = _get_settings()
    dynamic_mode = settings["penalty_mode"] == "Dinâmico"
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

    params["waiver_like"] = WAIVER_REMARK + "%"

    if cint(with_penalty):
        # "Com Multa": a multa line still standing on the invoice ("Adicionar à
        # Factura"), or in Dinâmico mode an unpaid invoice past the grace period.
        penalty_conds = [f"{_OPEN_PENALTY_SQL} > 0"]
        if dynamic_mode:
            params["penalty_cutoff"] = add_days(today_val, -settings["penalty_grace_days"])
            penalty_conds.append(
                "((si.docstatus = 0 AND si.grand_total > 0) OR (si.docstatus = 1 AND si.outstanding_amount > 0))"
                " AND si.due_date < %(penalty_cutoff)s"
            )
        conditions.append("(" + " OR ".join(f"({c})" for c in penalty_conds) + ")")

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
            {_OPEN_PENALTY_SQL} AS penalty_amount
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

        # Display-only multa for Dinâmico mode — kept apart from penalty_amount,
        # which the payment dialog treats as a real line it can waive.
        r.dynamic_penalty = 0
        if dynamic_mode and not flt(r.penalty_amount):
            owed = flt(r.grand_total) if r.docstatus == 0 else flt(r.outstanding_amount)
            if owed > 0:
                factor = _compute_penalty(r.due_date, settings)["penalty_amount_factor"]
                r.dynamic_penalty = round(owed * factor, 2)

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


def _invoice_types(names):
    """
    What each invoice is for, so the extrato reads clearly. Source documents
    keep a sales_invoice back-link; Inscrição/Renovação win over the
    Adiantamento they may have created for months paid upfront.
    """
    if not names:
        return {}
    names = tuple(names)
    types = {}

    rows = frappe.db.sql(
        """
        SELECT name, escola_billing_cycle, escola_is_addon_invoice,
               escola_mes_referencia, escola_advance_payment
        FROM `tabSales Invoice` WHERE name IN %s
        """,
        (names,), as_dict=True,
    )
    for r in rows:
        mes = f" · {r.escola_mes_referencia}" if r.escola_mes_referencia else ""
        if r.escola_billing_cycle:
            types[r.name] = (_("Extras") if r.escola_is_addon_invoice else _("Propina")) + mes
        elif r.escola_advance_payment:
            types[r.name] = _("Adiantamento")

    for doctype, label in (("Adiantamento De Pagamento", _("Adiantamento")),
                           ("Renovacao De Matricula", _("Renovação")),
                           ("Inscricao", _("Inscrição"))):
        for inv in frappe.get_all(doctype, filters={"sales_invoice": ["in", names], "docstatus": 1},
                                  pluck="sales_invoice"):
            types[inv] = label
    return types


def _invoice_payments(names):
    """
    Every way an invoice gets paid, newest first:
      - Payment Entries (Registar Pagamento, Make → Payment Entry)
      - POS invoices, paid inside the invoice itself (no Payment Entry)
      - Journal Entries against the invoice (multa waivers, manual entries)
    """
    names = tuple(names)
    payments = frappe.db.sql(
        """
        SELECT pe.name, 'Payment Entry' AS doctype, pe.posting_date, pe.creation,
               pe.mode_of_payment, per.reference_name AS invoice, per.allocated_amount AS amount
        FROM `tabPayment Entry Reference` per
        JOIN `tabPayment Entry` pe ON pe.name = per.parent
        WHERE pe.docstatus = 1 AND per.reference_doctype = 'Sales Invoice'
          AND per.reference_name IN %s
        """,
        (names,), as_dict=True,
    )

    pos_rows = frappe.db.sql(
        """
        SELECT si.name, si.posting_date, si.creation, si.change_amount,
               sip.mode_of_payment, sip.amount
        FROM `tabSales Invoice` si
        JOIN `tabSales Invoice Payment` sip ON sip.parent = si.name AND sip.parenttype = 'Sales Invoice'
        WHERE si.docstatus = 1 AND si.is_pos = 1 AND si.name IN %s AND sip.amount > 0
        ORDER BY si.name, sip.idx
        """,
        (names,), as_dict=True,
    )
    change_left = {}
    for r in pos_rows:
        # Change handed back is paid in, not kept — take it off the first rows.
        change_left.setdefault(r.name, flt(r.change_amount))
        amount = flt(r.amount)
        taken = min(change_left[r.name], amount)
        change_left[r.name] -= taken
        if amount - taken > 0:
            payments.append(frappe._dict(
                name=r.name, doctype="Sales Invoice", posting_date=r.posting_date, creation=r.creation,
                mode_of_payment=f"{r.mode_of_payment} (POS)", invoice=r.name, amount=amount - taken,
            ))

    payments += [
        frappe._dict(r, doctype="Journal Entry", mode_of_payment=(
            _("Dispensa de multa") if (r.user_remark or "").startswith(WAIVER_REMARK)
            else _("Lançamento contabilístico")))
        for r in frappe.db.sql(
            """
            SELECT je.name, je.posting_date, je.creation, je.user_remark,
                   jea.reference_name AS invoice, jea.credit_in_account_currency AS amount
            FROM `tabJournal Entry Account` jea
            JOIN `tabJournal Entry` je ON je.name = jea.parent
            WHERE je.docstatus = 1 AND jea.reference_type = 'Sales Invoice'
              AND jea.reference_name IN %s AND jea.credit_in_account_currency > 0
            """,
            (names,), as_dict=True,
        )
    ]

    payments.sort(key=lambda p: (getdate(p.posting_date), p.creation), reverse=True)
    for p in payments:
        p.pop("creation", None)
        p.pop("user_remark", None)
    return payments


@frappe.whitelist()
def get_student_statement(student, limit=12, full=0):
    """
    Mini extrato for the "Aluno" modal on Monitor de Facturas / Central de
    Pagamentos: student header, last invoices (any origin — mensalidade,
    inscrição, renovação…) with their multa, last payments, and totals.
    Drafts count as owed by their grand_total (their outstanding is unset).

    full=1 (printed extrato on the Student form): every invoice and payment,
    plus the school header.
    """
    full = cint(full)
    from escola.escola.doctype.student.student import get_student_invoices

    st = frappe.db.get_value(
        "Student", student,
        ["name", "full_name", "student_code", "current_status", "financial_status",
         "current_school_class", "current_class_group", "phone", "primary_guardian"],
        as_dict=True,
    )
    if not st:
        frappe.throw(frappe._("Aluno {0} não encontrado.").format(student))

    if st.current_class_group:
        st.turma_name = frappe.db.get_value("Class Group", st.current_class_group, "group_name")
    if st.primary_guardian:
        st.guardian_phone = frappe.db.get_value("Guardian", st.primary_guardian, "phone")

    data = get_student_invoices(student)
    names = [i["name"] for i in data["invoices"]]

    penalties = {}
    payments = []
    if names:
        # Multa still standing per invoice (lines minus Journal Entry waivers)
        penalties = dict(frappe.db.sql(
            f"""
            SELECT si.name, {_OPEN_PENALTY_SQL}
            FROM `tabSales Invoice` si
            WHERE si.name IN %(names)s
            """,
            {"names": tuple(names), "waiver_like": WAIVER_REMARK + "%"},
        ))
        payments = _invoice_payments(names)
        if not full:
            payments = payments[:10]

    types = _invoice_types(names)
    owed = 0.0
    for i in data["invoices"]:
        i["tipo"] = types.get(i["name"], _("Outro"))
        i["multa"] = flt(penalties.get(i["name"]))
        i["owed"] = i["grand_total"] if i["status"] == "Rascunho" else i["outstanding"]
        owed += i["owed"]

    summary = data["summary"]
    summary["total_owed"] = round(owed, 2)
    # Money actually received — a multa waiver / journal entry isn't a payment
    summary["last_payment"] = next((p for p in payments if p.doctype != "Journal Entry"), None)

    out = {
        "student": st,
        "invoices": data["invoices"] if full else data["invoices"][: cint(limit) or 12],
        "payments": payments,
        "summary": summary,
    }
    if full:
        out["school"] = frappe.db.get_value(
            "School Settings", "School Settings",
            ["school_name", "school_logo", "school_nif", "school_phone",
             "school_email", "school_address"],
            as_dict=True,
        )
    return out
