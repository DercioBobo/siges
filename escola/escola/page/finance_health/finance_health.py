"""
Saúde Financeira — a list of checks that each surface something the finance
team should look at. Every check returns rows in one shared shape so the page
renders them all the same way:

    {"ref": <what the fix acts on, or None>, "student": ..., "student_name": ...,
     "turma": ..., "docs": [[doctype, name], ...], "amount": float, "detail": str}

Checks with a `fix` are "Dados incorrectos" the system can correct; the rest
are "Atenção" items that need a human decision (contact the family, etc.).
Fixes always re-check the row before acting, so a stale page can't cancel an
invoice that was paid in the meantime.
"""

import json

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, today

FIX_ROLES = ("Diretor Escolar", "Accounts Manager", "System Manager")
DEPARTED = ("Transferido", "Desistente")

# Owed: drafts by grand_total (outstanding is unset before submit),
# submitted by outstanding_amount.
OWED = "((si.docstatus = 0 AND si.grand_total > 0) OR (si.docstatus = 1 AND si.outstanding_amount > 0))"
OWED_AMOUNT = "(CASE WHEN si.docstatus = 0 THEN si.grand_total ELSE si.outstanding_amount END)"
REGULAR = ("IFNULL(si.escola_billing_cycle, '') != '' "
           "AND COALESCE(si.escola_is_addon_invoice, 0) = 0")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _attach_students(rows):
    """Fill student_name / turma on rows that only carry `student`."""
    names = list({r["student"] for r in rows if r.get("student")})
    if not names:
        return rows
    info = {
        s.name: s for s in frappe.db.sql(
            """
            SELECT st.name, st.full_name, cg.group_name
            FROM `tabStudent` st
            LEFT JOIN `tabClass Group` cg ON cg.name = st.current_class_group
            WHERE st.name IN %s
            """,
            (tuple(names),), as_dict=True,
        )
    }
    for r in rows:
        s = info.get(r.get("student"))
        r["student_name"] = s.full_name if s else r.get("student")
        r["turma"] = (s.group_name if s else None) or ""
    rows.sort(key=lambda r: (r.get("student_name") or "").lower())
    return rows


def _row(student, docs, amount=0, detail="", ref=None):
    return {"ref": ref, "student": student, "docs": docs,
            "amount": round(flt(amount), 2), "detail": detail}


def _void_invoice(name, note):
    """Delete a draft / cancel an unpaid submitted invoice. Refuses paid ones."""
    from escola.escola.doctype.billing_cycle.billing_cycle import _unlink_from_generation_log

    inv = frappe.db.get_value(
        "Sales Invoice", name, ["docstatus", "grand_total", "outstanding_amount"], as_dict=True
    )
    if not inv or inv.docstatus == 2:
        return
    if inv.docstatus == 1:
        if flt(inv.outstanding_amount) < flt(inv.grand_total):
            frappe.throw(_("A factura {0} tem pagamentos — não pode ser anulada aqui.").format(name))
        frappe.get_doc("Sales Invoice", name).cancel()
    else:
        _unlink_from_generation_log(name, note)
        frappe.delete_doc("Sales Invoice", name, ignore_permissions=True)


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def q_duplicates():
    rows = frappe.db.sql(
        f"""
        SELECT si.name, si.escola_student AS student, si.creation, si.docstatus,
               si.grand_total, si.outstanding_amount,
               COALESCE(NULLIF(si.escola_mes_referencia, ''),
                        CAST(MONTH(si.posting_date) AS CHAR)) AS mes,
               YEAR(COALESCE(si.due_date, si.posting_date)) AS yr
        FROM `tabSales Invoice` si
        WHERE si.docstatus IN (0, 1) AND {REGULAR}
          AND IFNULL(si.escola_student, '') != ''
        ORDER BY si.creation DESC
        """,
        as_dict=True,
    )
    groups = {}
    for r in rows:
        groups.setdefault((r.student, r.mes, r.yr), []).append(r)

    out = []
    for (student, mes, yr), g in groups.items():
        if len(g) < 2:
            continue
        older = g[1:]  # newest first — keep g[0]
        removable = [r.name for r in older
                     if not (r.docstatus == 1 and flt(r.outstanding_amount) < flt(r.grand_total))]
        detail = _("{0} facturas para {1}/{2} — mantém {3}").format(len(g), mes, yr, g[0].name)
        if len(removable) < len(older):
            detail += " · " + _("cópia antiga com pagamento, rever")
        out.append(_row(
            student, [["Sales Invoice", r.name] for r in g],
            sum(flt(r.grand_total) for r in older), detail,
            ref=",".join(removable) or None,
        ))
    return out


def fix_duplicates(ref):
    for name in ref.split(","):
        _void_invoice(name, _("Factura eliminada — duplicada (Saúde Financeira)."))


def q_departed():
    rows = frappe.db.sql(
        f"""
        SELECT st.name AS student, st.current_status,
               GROUP_CONCAT(si.name ORDER BY si.posting_date) AS invoices,
               SUM({OWED_AMOUNT}) AS owed
        FROM `tabStudent` st
        JOIN `tabSales Invoice` si ON si.escola_student = st.name
        WHERE st.current_status IN %(departed)s AND {OWED}
        GROUP BY st.name
        """,
        {"departed": DEPARTED}, as_dict=True,
    )
    return [
        _row(r.student, [["Sales Invoice", n] for n in r.invoices.split(",")], r.owed,
             _("Aluno {0} com facturas em aberto").format(r.current_status), ref=r.student)
        for r in rows
    ]


def fix_departed(ref):
    from escola.escola.doctype.billing_cycle.billing_cycle import void_open_invoices_for_student

    result = void_open_invoices_for_student(ref)
    if result["errors"]:
        frappe.throw("<br>".join(result["errors"]))


def q_penalty_leftover():
    from escola.escola.payment_actions import _invoices_with_unpaid_penalty_only

    return [
        _row(r.escola_student, [["Sales Invoice", r.name]], r.outstanding_amount,
             _("Propina paga, falta só a multa ({0})").format(flt(r.multa)), ref=r.name)
        for r in _invoices_with_unpaid_penalty_only()
    ]


def fix_penalty_leftover(ref):
    from escola.escola.payment_actions import waive_submitted_penalty

    waive_submitted_penalty(ref)


def q_bad_dates():
    rows = frappe.db.sql(
        """
        SELECT si.name, si.escola_student AS student, si.posting_date, si.due_date, si.grand_total
        FROM `tabSales Invoice` si
        WHERE si.docstatus = 0
          AND si.due_date IS NOT NULL
          AND (
                si.due_date < si.posting_date
             OR EXISTS (SELECT 1 FROM `tabPayment Schedule` ps
                        WHERE ps.parent = si.name AND ps.parenttype = 'Sales Invoice'
                          AND ps.due_date != si.due_date)
          )
        """,
        as_dict=True,
    )
    return [
        _row(r.student, [["Sales Invoice", r.name]], r.grand_total,
             _("Emissão {0}, vencimento {1} ou plano de pagamento desalinhado").format(
                 r.posting_date, r.due_date),
             ref=r.name)
        for r in rows
    ]


def fix_bad_dates(ref):
    from escola.escola.doctype.billing_cycle.penalty import _repair_draft_dates

    inv = frappe.get_doc("Sales Invoice", ref)
    if inv.docstatus != 0:
        return
    inv.set_posting_time = 1
    _repair_draft_dates(inv)
    inv.save(ignore_permissions=True)


def q_unallocated_payments():
    rows = frappe.db.sql(
        """
        SELECT pe.name, pe.posting_date, pe.unallocated_amount, c.escola_student AS student
        FROM `tabPayment Entry` pe
        JOIN `tabCustomer` c ON c.name = pe.party
        WHERE pe.docstatus = 1 AND pe.party_type = 'Customer'
          AND pe.unallocated_amount > 0
          AND IFNULL(c.escola_student, '') != ''
        """,
        as_dict=True,
    )
    return [
        _row(r.student, [["Payment Entry", r.name]], r.unallocated_amount,
             _("Pagamento de {0} sem factura associada").format(r.posting_date))
        for r in rows
    ]


def q_never_paid():
    rows = frappe.db.sql(
        f"""
        SELECT si.escola_student AS student, COUNT(*) AS n, SUM({OWED_AMOUNT}) AS owed,
               GROUP_CONCAT(si.name ORDER BY si.posting_date) AS invoices
        FROM `tabSales Invoice` si
        JOIN `tabStudent` st ON st.name = si.escola_student
        WHERE st.current_status = 'Activo' AND {REGULAR}
          AND si.docstatus IN (0, 1) AND {OWED} AND si.due_date < %(today)s
          AND NOT EXISTS (
              SELECT 1 FROM `tabSales Invoice` p
              WHERE p.escola_student = si.escola_student AND p.docstatus = 1
                AND IFNULL(p.escola_billing_cycle, '') != ''
                AND p.outstanding_amount < p.grand_total
          )
        GROUP BY si.escola_student
        """,
        {"today": today()}, as_dict=True,
    )
    return [
        _row(r.student, [["Sales Invoice", n] for n in r.invoices.split(",")], r.owed,
             _("{0} mensalidade(s) vencida(s), nenhum pagamento registado").format(r.n))
        for r in rows
    ]


def q_overdue_2plus():
    rows = frappe.db.sql(
        f"""
        SELECT si.escola_student AS student, COUNT(*) AS n, SUM({OWED_AMOUNT}) AS owed,
               GROUP_CONCAT(si.name ORDER BY si.posting_date) AS invoices,
               GROUP_CONCAT(IFNULL(si.escola_mes_referencia, '') ORDER BY si.posting_date
                            SEPARATOR ', ') AS meses
        FROM `tabSales Invoice` si
        JOIN `tabStudent` st ON st.name = si.escola_student
        WHERE st.current_status = 'Activo' AND {REGULAR}
          AND si.docstatus IN (0, 1) AND {OWED} AND si.due_date < %(today)s
        GROUP BY si.escola_student
        HAVING COUNT(*) >= 2
        """,
        {"today": today()}, as_dict=True,
    )
    return [
        _row(r.student, [["Sales Invoice", n] for n in r.invoices.split(",")], r.owed,
             _("{0} meses em atraso: {1}").format(r.n, r.meses.strip(", ") or "—"))
        for r in rows
    ]


def q_gap_paid_after():
    rows = frappe.db.sql(
        f"""
        SELECT * FROM (
            SELECT si.name, si.escola_student AS student, si.posting_date,
                   si.escola_mes_referencia AS mes, {OWED_AMOUNT} AS owed,
                   (SELECT p.name FROM `tabSales Invoice` p
                    WHERE p.escola_student = si.escola_student AND p.docstatus = 1
                      AND IFNULL(p.escola_billing_cycle, '') != ''
                      AND p.posting_date > si.posting_date
                      AND p.outstanding_amount < p.grand_total
                    ORDER BY p.posting_date LIMIT 1) AS later_paid
            FROM `tabSales Invoice` si
            WHERE {REGULAR} AND si.docstatus IN (0, 1) AND {OWED}
              AND si.due_date < %(today)s
        ) t
        WHERE t.later_paid IS NOT NULL
        """,
        {"today": today()}, as_dict=True,
    )
    return [
        _row(r.student, [["Sales Invoice", r.name], ["Sales Invoice", r.later_paid]], r.owed,
             _("{0} por pagar, mas {1} (posterior) foi paga — pagamento não registado?").format(
                 r.mes or r.posting_date, r.later_paid),
             ref=r.name)
        for r in rows
    ]


def fix_gap_paid_after(ref):
    _void_invoice(ref, _("Factura eliminada — paga fora do sistema (Saúde Financeira)."))


def q_generation_errors():
    rows = frappe.db.sql(
        """
        SELECT log.student, log.reason, bc.name AS cycle, bc.posting_date
        FROM `tabBilling Cycle Student Log` log
        JOIN `tabBilling Cycle` bc ON bc.name = log.parent
        JOIN `tabStudent` st ON st.name = log.student
        WHERE log.status = 'Erro' AND bc.status != 'Cancelado'
          AND bc.posting_date >= %(since)s
          AND st.current_status = 'Activo'
        """,
        {"since": add_days(today(), -60)}, as_dict=True,
    )
    return [
        _row(r.student, [["Billing Cycle", r.cycle]], 0,
             _("{0}: {1}").format(r.posting_date, (r.reason or "").strip()))
        for r in rows
    ]


CHECKS = [
    # --- Dados incorrectos: the system can fix these -------------------------
    {"key": "duplicates", "group": "Dados incorrectos", "severity": "danger",
     "label": "Facturas duplicadas", "query": q_duplicates, "fix": fix_duplicates,
     "fix_label": "Remover cópias antigas",
     "description": "O mesmo aluno tem mais do que uma mensalidade para o mesmo mês. "
                    "A correcção mantém a factura mais recente e remove as cópias antigas sem pagamento."},
    {"key": "departed", "group": "Dados incorrectos", "severity": "danger",
     "label": "Saíram com facturas em aberto", "query": q_departed, "fix": fix_departed,
     "fix_label": "Anular facturas",
     "description": "Alunos Transferidos ou Desistentes que ainda têm facturas por pagar. "
                    "Rascunhos são eliminados e facturas sem pagamento canceladas."},
    {"key": "penalty_leftover", "group": "Dados incorrectos", "severity": "warning",
     "label": "Só falta a multa", "query": q_penalty_leftover, "fix": fix_penalty_leftover,
     "fix_label": "Dispensar multa",
     "description": "A propina foi paga mas a multa ficou em dívida. "
                    "A correcção abate a multa com um lançamento contabilístico (sem nota de crédito)."},
    {"key": "bad_dates", "group": "Dados incorrectos", "severity": "warning",
     "label": "Datas inválidas", "query": q_bad_dates, "fix": fix_bad_dates,
     "fix_label": "Corrigir datas",
     "description": "Rascunhos cujo vencimento é anterior à emissão ou cujo plano de pagamento não "
                    "coincide — o ERPNext recusa guardá-los (ex.: aplicar multa)."},
    {"key": "gap_paid_after", "group": "Dados incorrectos", "severity": "warning",
     "label": "Mês por pagar com seguintes pagos", "query": q_gap_paid_after,
     "fix": fix_gap_paid_after, "fix_label": "Anular (pago fora do sistema)",
     "description": "Uma mensalidade vencida está por pagar, mas uma posterior do mesmo aluno foi paga — "
                    "normalmente um pagamento que não foi registado. Confirme antes de anular."},
    # --- Atenção: need a human decision --------------------------------------
    {"key": "never_paid", "group": "Atenção", "severity": "danger",
     "label": "Nunca pagaram", "query": q_never_paid,
     "description": "Alunos activos com mensalidades vencidas e nenhum pagamento de mensalidade registado."},
    {"key": "overdue_2plus", "group": "Atenção", "severity": "warning",
     "label": "2+ meses em atraso", "query": q_overdue_2plus,
     "description": "Alunos activos com duas ou mais mensalidades vencidas por pagar."},
    {"key": "unallocated_payments", "group": "Atenção", "severity": "info",
     "label": "Pagamentos não alocados", "query": q_unallocated_payments,
     "description": "Pagamentos recebidos com saldo não associado a nenhuma factura — "
                    "aloque-os a uma factura em dívida (Reconciliação de Pagamentos)."},
    {"key": "generation_errors", "group": "Atenção", "severity": "info",
     "label": "Erros na geração", "query": q_generation_errors,
     "description": "Alunos activos que ficaram sem factura num ciclo dos últimos 60 dias por erro."},
]
CHECKS_BY_KEY = {c["key"]: c for c in CHECKS}


def _meta(c, count=None):
    return {
        "key": c["key"], "group": c["group"], "severity": c["severity"],
        "label": _(c["label"]), "description": _(c["description"]),
        "fixable": bool(c.get("fix")), "fix_label": _(c.get("fix_label") or ""),
        "count": count,
    }


def _students_for_ref(ref):
    """A ref is a Student name or comma-separated invoice names."""
    if frappe.db.exists("Student", ref):
        return {ref}
    return {
        s for s in (frappe.db.get_value("Sales Invoice", n, "escola_student") for n in ref.split(","))
        if s
    }


def _can_fix():
    return bool(set(frappe.get_roles()) & set(FIX_ROLES))


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_overview():
    checks = []
    for c in CHECKS:
        try:
            count = len(c["query"]())
        except Exception:
            frappe.log_error(title=f"Saúde Financeira — erro no teste {c['key']}")
            count = None
        checks.append(_meta(c, count))
    return {"checks": checks, "can_fix": _can_fix()}


@frappe.whitelist()
def get_check(key):
    c = CHECKS_BY_KEY.get(key)
    if not c:
        frappe.throw(_("Teste desconhecido: {0}").format(key))
    rows = _attach_students(c["query"]())
    return {"check": _meta(c, len(rows)), "rows": rows, "can_fix": _can_fix()}


@frappe.whitelist()
def apply_fix(key, refs):
    """Apply a check's fix to each ref; one bad row never blocks the others."""
    frappe.only_for(FIX_ROLES)
    c = CHECKS_BY_KEY.get(key)
    if not c or not c.get("fix"):
        frappe.throw(_("Este teste não tem correcção automática."))
    if isinstance(refs, str):
        refs = json.loads(refs)

    from escola.escola.doctype.billing_cycle.penalty import update_student_financial_status

    done, errors, students = 0, [], set()
    for ref in refs or []:
        if not ref:
            continue
        students |= _students_for_ref(ref)
        try:
            frappe.db.savepoint("finance_fix")
            c["fix"](ref)
            frappe.db.commit()
            done += 1
        except Exception as e:
            frappe.db.rollback(save_point="finance_fix")
            errors.append(f"{ref}: {frappe.utils.strip_html(str(e))}")

    for s in students:
        try:
            update_student_financial_status(s)
        except Exception:
            pass

    return {"done": done, "errors": errors}
