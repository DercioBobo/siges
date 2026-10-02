"""Months paid in advance at enrolment (Inscrição) or renewal (Renovação de Matrícula).

Both doctypes carry the same fields — advance_periods (Adiantamento Period Line),
advance_gross_total, advance_discount_percent, advance_total, total_to_pay and
adiantamento. The months go on the same Sales Invoice as the enrolment/renewal fee;
a submitted Adiantamento De Pagamento (flagged ``invoice_from_enrollment`` so it
doesn't invoice again) records them so the billing cycle skips those months.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, today

from escola.escola.doctype.adiantamento_de_pagamento.adiantamento_de_pagamento import (
    _DISCOUNT_FULL_YEAR,
    _DISCOUNT_SIX_PLUS,
    _MIN_PERIODS_DISCOUNT,
    _resolve_item_code,
    count_class_year_periods,
    discount_tier,
    periods_for_class,
)


def get_options(academic_year, school_class, fee_amount):
    """Months available for ``school_class`` in the year, plus pricing info for the form."""
    return {
        "periods": periods_for_class(school_class, academic_year),
        "full_year_periods": count_class_year_periods(school_class, academic_year),
        "discount": {
            "full_year": _DISCOUNT_FULL_YEAR,
            "six_plus": _DISCOUNT_SIX_PLUS,
            "min_periods": _MIN_PERIODS_DISCOUNT,
        },
        "fee_amount": flt(fee_amount),
    }


def compute_totals(doc, academic_year, school_class, fee_amount, exempt=False):
    """Validate and price the selected months from the class's billing schedule
    (never from the client), apply the Adiantamento discount tiers and set totals."""
    if exempt or not school_class:
        doc.set("advance_periods", [])

    if doc.advance_periods:
        available = {
            (p["posting_date"], p["billing_mode"]): p
            for p in periods_for_class(school_class, academic_year)
        }
        seen = set()
        for row in doc.advance_periods:
            key = (str(getdate(row.posting_date)), row.billing_mode)
            if key in seen:
                frappe.throw(_("Mensalidade duplicada: <b>{0}</b>.").format(row.period_label))
            seen.add(key)
            period = available.get(key)
            if not period:
                frappe.throw(
                    _("A mensalidade <b>{0}</b> não pertence ao plano de cobrança da Classe <b>{1}</b> "
                      "em <b>{2}</b>. Volte a seleccionar as mensalidades.").format(
                        row.period_label, school_class, academic_year
                    ),
                    title=_("Mensalidade inválida"),
                )
            row.period_label = period["period_label"]
            row.gross_amount = flt(period["gross_amount"])
        doc.advance_periods.sort(key=lambda r: str(r.posting_date))
        for i, row in enumerate(doc.advance_periods, start=1):
            row.idx = i

    n = len(doc.advance_periods or [])
    pct = 0.0
    if n:
        pct, _reason = discount_tier(n, count_class_year_periods(school_class, academic_year))
    doc.advance_gross_total = sum(flt(r.gross_amount) for r in (doc.advance_periods or []))
    doc.advance_discount_percent = pct
    doc.advance_total = doc.advance_gross_total * (1 - pct / 100.0)
    doc.total_to_pay = flt(fee_amount) + doc.advance_total


def validate_not_in_debt(doc, student):
    """Fail on save (not halfway through submit) when the Adiantamento would be refused."""
    if not doc.advance_periods or not student:
        return
    status = frappe.db.get_value("Student", student, "financial_status") or "Regular"
    if status != "Regular":
        frappe.throw(
            _("O aluno tem pagamentos em atraso (<b>{0}</b>). Regularize a dívida antes de "
              "pagar mensalidades antecipadas, ou retire as mensalidades seleccionadas.").format(_(status)),
            title=_("Mensalidades antecipadas bloqueadas"),
        )


def create_adiantamento(doc, student, academic_year, school_class):
    """Insert (not submit) the Adiantamento recording the months. None when no months."""
    if not doc.advance_periods or not student:
        return None
    adp = frappe.get_doc({
        "doctype": "Adiantamento De Pagamento",
        "payment_date": today(),
        "academic_year": academic_year,
        "student": student,
        "school_class": school_class,
        "is_pos": 0,
        "notes": _("Pago em {0} {1}.").format(_(doc.doctype), doc.name),
        "periods": [
            {
                "period_label": r.period_label,
                "posting_date": r.posting_date,
                "billing_mode": r.billing_mode,
                "gross_amount": r.gross_amount,
            }
            for r in doc.advance_periods
        ],
    })
    adp.flags.invoice_from_enrollment = True
    adp.flags.keep_school_class = True
    adp.insert(ignore_permissions=True)
    return adp


def append_month_lines(si, adp):
    """Add one invoice line per advanced month, plus the Adiantamento discount."""
    month_item = _resolve_item_code(adp.school_class, adp.periods)
    for p in adp.periods:
        label = _("Mensalidade — {0}").format(p.period_label)
        si.append("items", {
            "item_code":   month_item,
            "item_name":   label,
            "description": label,
            "qty":         1,
            "rate":        flt(p.gross_amount),
        })
    if flt(adp.discount_total) > 0.001:
        si.discount_amount = flt(adp.discount_total)
    try:
        si.escola_advance_payment = adp.name
    except Exception:
        pass


def submit_adiantamento(doc, adp, inv):
    adp.sales_invoice = inv.name if inv else None
    adp.flags.ignore_permissions = True
    adp.submit()
    doc.db_set("adiantamento", adp.name)
    for row in doc.advance_periods:
        row.db_set("invoice", adp.sales_invoice)


def cancel_adiantamento(doc):
    """Cancel the Adiantamento and drop its links to the shared invoice, so the
    invoice can still be deleted/cancelled by the parent document."""
    if not doc.adiantamento:
        return
    adp = frappe.get_doc("Adiantamento De Pagamento", doc.adiantamento)
    if adp.docstatus == 1:
        adp.flags.invoice_from_enrollment = True
        adp.flags.ignore_permissions = True
        adp.cancel()
    adp.db_set("sales_invoice", None)
    for p in adp.periods:
        p.db_set("invoice", None)
    for row in doc.advance_periods:
        row.db_set("invoice", None)
    if doc.sales_invoice and frappe.db.get_value("Sales Invoice", doc.sales_invoice, "escola_advance_payment"):
        frappe.db.set_value("Sales Invoice", doc.sales_invoice, "escola_advance_payment", None)
