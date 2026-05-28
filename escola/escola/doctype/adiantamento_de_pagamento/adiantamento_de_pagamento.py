import calendar
from datetime import date, timedelta

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, flt, getdate, today


# Discount tiers
_DISCOUNT_FULL_YEAR = 10.0   # pay ALL periods of the year in one shot
_DISCOUNT_SIX_PLUS  = 5.0    # pay 6 or more periods in one payment
_MIN_PERIODS_DISCOUNT = 6


class AdiantamentoDePagamento(Document):

    def before_save(self):
        self._fetch_student_info()
        self._recalculate_summary()

    def validate(self):
        self._validate_no_overdue_debt()
        if not self.periods:
            frappe.throw(
                _("Seleccione pelo menos um período. Use o botão <b>Carregar Períodos</b>."),
                title=_("Sem períodos"),
            )
        self._validate_no_duplicate_periods()
        self._validate_periods_not_covered()
        self._validate_payment()
        self._validate_no_duplicate_adiantamento()

    def on_submit(self):
        from escola.escola.invoice_utils import invoice_success_msg
        inv = self._create_invoice()
        self.db_set("sales_invoice", inv.name)
        frappe.msgprint(
            invoice_success_msg(inv.name, _("Adiantamento confirmado.")),
            title=_("Adiantamento concluído"),
            indicator="green",
        )

    def on_cancel(self):
        self._cancel_invoice()

    # ------------------------------------------------------------------

    def _validate_no_overdue_debt(self):
        if not self.student:
            return
        status = frappe.db.get_value("Student", self.student, "financial_status") or "Regular"
        if status != "Regular":
            frappe.throw(
                _("O aluno <b>{0}</b> tem dívidas em atraso (<b>{1}</b>). "
                  "Regularize os pagamentos em atraso antes de criar um adiantamento.").format(
                    self.student, _(status)
                ),
                title=_("Adiantamento bloqueado"),
            )

    def _fetch_student_info(self):
        if not self.student:
            return
        s = frappe.db.get_value(
            "Student", self.student,
            ["full_name", "current_school_class"],
            as_dict=True,
        )
        if s:
            self.student_full_name = s.full_name or ""
            self.school_class      = s.current_school_class or ""

    def _recalculate_summary(self):
        n = len(self.periods or [])
        self.total_periods = n
        self.gross_total   = sum(flt(p.gross_amount) for p in (self.periods or []))

        # Compute full_year_periods from active billing schedules
        full_year = _count_year_periods(self.student, self.academic_year)
        self.full_year_periods = full_year

        # Discount tier
        if n == full_year and n > 0:
            pct    = _DISCOUNT_FULL_YEAR
            reason = _("Ano Lectivo completo")
        elif n >= _MIN_PERIODS_DISCOUNT:
            pct    = _DISCOUNT_SIX_PLUS
            reason = _("{0} períodos ou mais").format(_MIN_PERIODS_DISCOUNT)
        else:
            pct    = 0.0
            reason = ""

        self.discount_percent = pct
        self.discount_reason  = reason
        self.discount_total   = self.gross_total * pct / 100.0
        self.net_total        = self.gross_total - self.discount_total

    def _validate_no_duplicate_periods(self):
        seen = set()
        for p in (self.periods or []):
            key = (str(p.posting_date), p.billing_mode)
            if key in seen:
                frappe.throw(
                    _("Período duplicado na tabela: <b>{0}</b> ({1}).").format(
                        p.period_label, p.billing_mode
                    ),
                    title=_("Período duplicado"),
                )
            seen.add(key)

    def _validate_periods_not_covered(self):
        for p in (self.periods or []):
            if _period_already_covered(self.student, p.billing_mode, getdate(p.posting_date), exclude_adiantamento=self.name):
                frappe.throw(
                    _("O período <b>{0}</b> já está coberto por uma factura ou adiantamento existente.").format(
                        p.period_label
                    ),
                    title=_("Período já coberto"),
                )

    def _validate_payment(self):
        if not self.is_pos:
            return
        if not self.payments:
            frappe.throw(
                _("Defina pelo menos um método de pagamento quando o modo POS está activo."),
                title=_("Pagamento em falta"),
            )
        total_paid = sum(flt(p.amount) for p in self.payments)
        if abs(total_paid - self.net_total) > 0.01:
            frappe.throw(
                _("O total dos métodos de pagamento ({0}) não corresponde ao Total a Pagar ({1}).").format(
                    frappe.format_value(total_paid, {"fieldtype": "Currency"}),
                    frappe.format_value(self.net_total, {"fieldtype": "Currency"}),
                ),
                title=_("Pagamento incorreto"),
            )

    def _validate_no_duplicate_adiantamento(self):
        """Prevent two active adiantamentos covering the same student+year+period overlap."""
        if not self.periods:
            return
        period_dates = [str(p.posting_date) for p in self.periods]
        for pd in period_dates:
            existing = frappe.db.sql("""
                SELECT adp.name
                FROM `tabAdiantamento Period Line` apl
                JOIN `tabAdiantamento De Pagamento` adp ON adp.name = apl.parent
                WHERE adp.student = %s
                  AND adp.docstatus = 1
                  AND adp.name != %s
                  AND apl.posting_date = %s
                LIMIT 1
            """, (self.student, self.name or "", pd))
            if existing:
                frappe.throw(
                    _("Já existe um Adiantamento activo que cobre um período seleccionado "
                      "(<b>{0}</b>).").format(existing[0][0]),
                    title=_("Sobreposição de adiantamentos"),
                )

    # ------------------------------------------------------------------

    def _create_invoice(self):
        from escola.escola.doctype.student.student import ensure_customer_for_student

        settings = frappe.get_single("School Settings")
        company   = (
            settings.get("default_company")
            or frappe.db.get_single_value("Global Defaults", "default_company")
        )
        due_days  = int(settings.get("invoice_due_days") or 30)
        due_date  = add_days(self.payment_date, due_days)

        customer = ensure_customer_for_student(self.student)

        # Resolve item_code: use first fee line for the student's class + billing mode,
        # fall back to the generic "Propina" item.
        item_code = _resolve_item_code(self.school_class, self.periods)

        si = frappe.new_doc("Sales Invoice")
        si.customer      = customer
        si.company       = company
        si.posting_date  = self.payment_date
        si.due_date      = due_date
        si.remarks       = _("Adiantamento de Pagamento — {0} — {1} período(s)").format(
            self.academic_year, self.total_periods
        )

        if self.is_pos and self.pos_profile:
            si.is_pos      = 1
            si.pos_profile = self.pos_profile

        try:
            si.escola_student           = self.student
            si.escola_advance_payment   = self.name
        except Exception:
            pass

        # One line per period so the Sales Invoice shows the full breakdown
        for p in self.periods:
            net_line = flt(p.gross_amount) * (1 - flt(self.discount_percent) / 100.0)
            si.append("items", {
                "item_code":   item_code,
                "item_name":   p.period_label,
                "description": p.period_label,
                "qty":         1,
                "rate":        net_line,
            })

        # Discount line (negative) to show the deduction explicitly
        if self.discount_total > 0.001:
            si.discount_amount = self.discount_total

        # POS payments
        if self.is_pos:
            for pmt in (self.payments or []):
                account = _get_payment_account(pmt.mode_of_payment, company)
                si.append("payments", {
                    "mode_of_payment": pmt.mode_of_payment,
                    "amount":          pmt.amount,
                    "account":         account,
                })

        si.insert(ignore_permissions=True)
        si.submit()

        # Back-fill invoice reference on each period row
        for p in self.periods:
            p.db_set("invoice", si.name)

        return si

    def _cancel_invoice(self):
        if not self.sales_invoice:
            return
        inv_status = frappe.db.get_value("Sales Invoice", self.sales_invoice, "docstatus")
        if inv_status == 0:
            frappe.delete_doc("Sales Invoice", self.sales_invoice, ignore_permissions=True)
            self.db_set("sales_invoice", None)
            frappe.msgprint(_("Factura de adiantamento eliminada."), indicator="orange")
        elif inv_status == 1:
            frappe.get_doc("Sales Invoice", self.sales_invoice).cancel()
            frappe.msgprint(_("Factura de adiantamento cancelada."), indicator="orange")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _count_year_periods(student, academic_year):
    """Count total billing periods for student's class in the given academic year."""
    from escola.escola.billing_forecast import _billing_periods

    school_class = frappe.db.get_value("Student", student, "current_school_class") if student else None
    if not school_class or not academic_year:
        return 0

    ay = frappe.db.get_value("Academic Year", academic_year, ["start_date", "end_date"], as_dict=True)
    if not ay or not ay.start_date or not ay.end_date:
        return 0

    ay_start = getdate(ay.start_date)
    ay_end   = getdate(ay.end_date)

    schedules = frappe.get_all(
        "Billing Schedule",
        filters={"school_class": school_class, "is_active": 1},
        fields=["name", "billing_mode", "invoice_day", "billing_month"],
    )
    inv_day = int(frappe.db.get_single_value("School Settings", "invoice_posting_day") or 25)

    total = 0
    for sched in schedules:
        day = int(sched.invoice_day or 0) or inv_day
        total += len(_billing_periods(sched, ay_start, ay_end, day))
    return total


def _period_already_covered(student, billing_mode, posting_date, exclude_adiantamento=None):
    """Return True if this period already has a non-cancelled invoice or an active adiantamento."""
    # Check billing-cycle invoices
    if billing_mode == "Mensal":
        period_sql = "YEAR(si.posting_date) = YEAR(%s) AND MONTH(si.posting_date) = MONTH(%s)"
        params = (student, billing_mode, posting_date, posting_date)
    elif billing_mode == "Trimestral":
        period_sql = "YEAR(si.posting_date) = YEAR(%s) AND QUARTER(si.posting_date) = QUARTER(%s)"
        params = (student, billing_mode, posting_date, posting_date)
    elif billing_mode == "Anual":
        period_sql = "YEAR(si.posting_date) = YEAR(%s)"
        params = (student, billing_mode, posting_date)
    else:
        period_sql = "si.posting_date = %s"
        params = (student, billing_mode, posting_date)

    inv_exists = frappe.db.sql(f"""
        SELECT 1
        FROM `tabSales Invoice` si
        JOIN `tabBilling Cycle` bc ON bc.name = si.escola_billing_cycle
        WHERE si.escola_student = %s
          AND si.docstatus != 2
          AND bc.billing_mode = %s
          AND {period_sql}
        LIMIT 1
    """, params)
    if inv_exists:
        return True

    # Check advance payment coverage
    excl = exclude_adiantamento or ""
    adv_exists = frappe.db.sql("""
        SELECT 1
        FROM `tabAdiantamento Period Line` apl
        JOIN `tabAdiantamento De Pagamento` adp ON adp.name = apl.parent
        WHERE adp.student = %s
          AND adp.docstatus = 1
          AND adp.name != %s
          AND apl.billing_mode = %s
          AND apl.posting_date = %s
        LIMIT 1
    """, (student, excl, billing_mode, posting_date))
    return bool(adv_exists)


def _resolve_item_code(school_class, periods):
    """Return item_code to use for Sales Invoice lines."""
    if periods:
        billing_mode = periods[0].billing_mode
    else:
        billing_mode = None

    if school_class and billing_mode:
        fs_name = frappe.db.get_value(
            "Fee Structure",
            {"school_class": school_class, "is_active": 1},
            "name",
        )
        if fs_name:
            line = frappe.db.get_value(
                "Fee Structure Line",
                {"parent": fs_name, "billing_mode": billing_mode},
                "item_code",
            )
            if line:
                return line

    # Fallback to default item
    return frappe.db.get_single_value("School Settings", "enrollment_fee_item_code") or "Propina"


def _get_payment_account(mode_of_payment, company):
    return frappe.db.get_value(
        "Mode of Payment Account",
        {"parent": mode_of_payment, "company": company},
        "default_account",
    )


# ---------------------------------------------------------------------------
# Whitelisted helpers (called from JS)
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_available_periods(student, academic_year):
    """
    Return all billing periods in the academic year for the student's class
    that are not yet covered by an invoice or an active adiantamento.
    Each item: {period_label, posting_date, billing_mode, gross_amount}.
    """
    from escola.escola.billing_forecast import _billing_periods

    school_class = frappe.db.get_value("Student", student, "current_school_class")
    if not school_class:
        return []

    ay = frappe.db.get_value("Academic Year", academic_year, ["start_date", "end_date"], as_dict=True)
    if not ay or not ay.start_date or not ay.end_date:
        return []

    ay_start = getdate(ay.start_date)
    ay_end   = getdate(ay.end_date)

    schedules = frappe.get_all(
        "Billing Schedule",
        filters={"school_class": school_class, "is_active": 1},
        fields=["name", "billing_mode", "invoice_day", "billing_month"],
    )
    if not schedules:
        return []

    fs_name = frappe.db.get_value(
        "Fee Structure",
        {"school_class": school_class, "is_active": 1},
        "name",
    )

    inv_day = int(frappe.db.get_single_value("School Settings", "invoice_posting_day") or 25)

    result = []
    for sched in schedules:
        day = int(sched.invoice_day or 0) or inv_day

        # Amount for this billing_mode
        fee_lines = frappe.get_all(
            "Fee Structure Line",
            filters={"parent": fs_name, "billing_mode": sched.billing_mode},
            fields=["amount"],
        ) if fs_name else []
        gross_amount = sum(float(ln.amount or 0) for ln in fee_lines)

        for p in _billing_periods(sched, ay_start, ay_end, day):
            posting_date = p["posting_date"]
            if not _period_already_covered(student, sched.billing_mode, posting_date):
                result.append({
                    "period_label": p["period_label"],
                    "posting_date": str(posting_date),
                    "billing_mode": sched.billing_mode,
                    "gross_amount": gross_amount,
                })

    result.sort(key=lambda x: x["posting_date"])
    return result
