import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, flt, getdate, today

from escola.escola import advance_months
from escola.escola.payment_actions import get_payment_account as _get_payment_account
from escola.escola.doctype.student.student import student_label


# ---------------------------------------------------------------------------
# Document class
# ---------------------------------------------------------------------------

class RenovacaoDeMatricula(Document):

    def validate(self):
        self._validate_student_status()
        self._validate_years()
        self._validate_not_duplicate()
        self._compute_advance_months()
        self._validate_payments()

    def on_submit(self):
        from escola.escola.invoice_utils import invoice_success_msg
        adp = advance_months.create_adiantamento(
            self, self.student, self.target_academic_year, self.target_school_class
        )
        inv = _create_renewal_invoice(self, adp)
        if adp:
            advance_months.submit_adiantamento(self, adp, inv)
        if inv:
            self.db_set("sales_invoice", inv.name)
            frappe.msgprint(
                invoice_success_msg(inv.name, _("Renovação confirmada.")),
                title=_("Renovação concluída"),
                indicator="green",
            )
        else:
            frappe.msgprint(
                _("Renovação confirmada. Configure o <b>Item da Taxa de Renovação</b> em Configurações da Escola para gerar a factura automaticamente."),
                title=_("Renovação concluída — sem factura"),
                indicator="orange",
            )

    def on_cancel(self):
        self._revert_sga()
        advance_months.cancel_adiantamento(self)
        if self.sales_invoice:
            inv_status = frappe.db.get_value("Sales Invoice", self.sales_invoice, "docstatus")
            if inv_status == 0:
                frappe.delete_doc("Sales Invoice", self.sales_invoice, ignore_permissions=True)
                self.db_set("sales_invoice", None)
                frappe.msgprint(_("Factura de renovação eliminada."), indicator="orange")
            else:
                frappe.msgprint(
                    _("A factura <b>{0}</b> já está submetida. Cancele-a manualmente se necessário.").format(
                        self.sales_invoice
                    ),
                    title=_("Factura não cancelada"),
                    indicator="orange",
                )

    def _revert_sga(self):
        """Close the active SGA in the target year and reset student status."""
        if not self.student or not self.target_academic_year:
            return

        sga_name = frappe.db.get_value(
            "Student Group Assignment",
            {"student": self.student, "academic_year": self.target_academic_year, "status": "Activa"},
            "name",
        )
        if sga_name:
            frappe.db.set_value("Student Group Assignment", sga_name, "status", "Encerrada")
            from escola.escola.doctype.student_group_assignment.student_group_assignment import (
                _roster_sync, _sync_student_current_turma,
            )
            sga = frappe.get_doc("Student Group Assignment", sga_name)
            _roster_sync(sga)
            _sync_student_current_turma(sga)
            frappe.msgprint(
                _("A alocação do aluno na turma do ano <b>{0}</b> foi encerrada.").format(
                    self.target_academic_year
                ),
                indicator="orange",
            )

        frappe.db.set_value(
            "Student", self.student, "current_status", "Pendente de Renovação",
            update_modified=False,
        )

    # ------------------------------------------------------------------

    def _compute_advance_months(self):
        """Months of the target year paid together with the renewal — opt-in only,
        since next year's class isn't certain until promotion."""
        if not self.pay_advance_months:
            self.set("advance_periods", [])
        elif not self.target_school_class:
            frappe.throw(
                _("Indique a <b>Classe no Próximo Ano</b> para calcular o valor das mensalidades."),
                title=_("Classe em falta"),
            )
        advance_months.compute_totals(
            self, self.target_academic_year, self.target_school_class,
            _renewal_fee_amount(self), exempt=self.is_bolsista,
        )
        advance_months.validate_not_in_debt(self, self.student)

    def _validate_student_status(self):
        status = frappe.db.get_value("Student", self.student, "current_status")
        if status == "Concluiu":
            frappe.throw(
                _("O aluno <b>{0}</b> concluiu todos os anos de escolaridade e não pode efectuar renovações.").format(
                    student_label(self.student)
                ),
                title=_("Aluno já concluiu"),
            )

    def _validate_years(self):
        if self.academic_year and self.target_academic_year:
            if self.academic_year == self.target_academic_year:
                frappe.throw(
                    _("O Ano Lectivo de Renovação deve ser diferente do Ano Lectivo de Origem."),
                    title=_("Anos lectivos inválidos"),
                )

    def _validate_payments(self):
        if not self.payments:
            frappe.throw(
                _("Preencha a tabela <b>Métodos de Pagamento</b>."),
                title=_("Pagamento obrigatório"),
            )

        for p in self.payments:
            if not p.mode_of_payment or flt(p.amount) <= 0:
                frappe.throw(
                    _("Linha {0} dos Métodos de Pagamento: indique o modo de pagamento e um valor maior que zero.").format(p.idx),
                    title=_("Pagamento inválido"),
                )

        # Bolsistas are not invoiced, so the total doesn't need to match the fee
        if frappe.db.get_value("Student", self.student, "is_bolsista"):
            return

        # total_to_pay = renewal fee + months paid in advance (see _compute_advance_months)
        expected = flt(self.total_to_pay)
        total = sum(flt(p.amount) for p in self.payments)
        if expected and abs(total - expected) > 0.009:
            frappe.throw(
                _("O total dos pagamentos ({0}) deve ser igual ao Total a Pagar ({1}).").format(
                    frappe.format_value(total, {"fieldtype": "Currency"}),
                    frappe.format_value(expected, {"fieldtype": "Currency"}),
                ),
                title=_("Valor incorrecto"),
            )

    def _validate_not_duplicate(self):
        existing = frappe.db.get_value(
            "Renovacao De Matricula",
            {
                "student":               self.student,
                "academic_year":         self.academic_year,
                "target_academic_year":  self.target_academic_year,
                "docstatus":             ("!=", 2),
                "name":                  ("!=", self.name),
            },
            "name",
        )
        if existing:
            frappe.throw(
                _(
                    "Já existe uma Renovação de Matrícula para o aluno <b>{0}</b> "
                    "neste percurso de anos: <b><a href='/app/renovacao-de-matricula/{1}'>{1}</a></b>."
                ).format(student_label(self.student), existing),
                title=_("Renovação duplicada"),
            )


# ---------------------------------------------------------------------------
# Invoice creation helper
# ---------------------------------------------------------------------------

def _renewal_fee_amount(doc):
    """Renewal fee charged on this Renovação (0 for bolsistas)."""
    if doc.is_bolsista or frappe.db.get_value("Student", doc.student, "is_bolsista"):
        return 0.0
    return flt(frappe.db.get_single_value("School Settings", "renewal_fee_amount"))


def predict_target_school_class(student, target_academic_year):
    """Next year's class, only when it is certain: the turma already assigned for
    that year (promotion done). No guessing — a student may repeat the year."""
    return frappe.db.get_value(
        "Student Group Assignment",
        {"student": student, "academic_year": target_academic_year, "status": "Activa"},
        "school_class",
    )


def _create_renewal_invoice(doc, adp=None):
    """Create a POS Sales Invoice for the renewal fee plus any months paid in advance
    (``adp``, the Adiantamento recording them). Returns the invoice or None."""
    from escola.escola.doctype.student.student import ensure_customer_for_student

    settings = frappe.get_single("School Settings")
    item_code = settings.get("renewal_fee_item_code")
    bill_fee = bool(item_code) and not frappe.db.get_value("Student", doc.student, "is_bolsista")
    if not bill_fee and not adp:
        return None

    try:
        customer = ensure_customer_for_student(doc.student)
    except Exception as e:
        frappe.throw(
            _("Não foi possível obter o cliente do aluno: {0}").format(str(e)),
            title=_("Erro ao criar factura"),
        )

    company = (
        frappe.db.get_single_value("School Settings", "default_company")
        or frappe.db.get_single_value("Global Defaults", "default_company")
    )
    due_days    = int(frappe.db.get_single_value("School Settings", "invoice_due_days") or 30)
    today_date  = today()
    due_date    = add_days(today_date, due_days)
    # Months paid in advance are paid by definition — always submit those invoices.
    auto_submit = int(settings.get("auto_submit_renewal_invoice") or 0) or bool(adp)
    fee_amount  = float(settings.get("renewal_fee_amount") or 0)
    is_pos      = int(settings.get("renewal_is_pos") or 0)
    pos_profile = settings.get("renewal_pos_profile") or ""
    use_pos     = bool(is_pos and pos_profile)
    description = _("Renovação de Matrícula {0}").format(doc.target_academic_year)

    si = frappe.new_doc("Sales Invoice")
    si.customer      = customer
    si.company       = company
    si.posting_date  = today_date
    si.due_date      = due_date
    si.remarks       = description
    if adp:
        si.remarks = _("{0} — {1} mensalidade(s)").format(description, adp.total_periods)

    if use_pos:
        si.is_pos      = 1
        si.pos_profile = pos_profile

    try:
        si.escola_student = doc.student
    except Exception:
        pass

    if bill_fee:
        si.append("items", {
            "item_code":   item_code,
            "item_name":   description,
            "description": description,
            "qty":         1,
            "rate":        fee_amount,
        })

    if adp:
        advance_months.append_month_lines(si, adp)

    # Copy payment methods from the Renovação doc (only relevant when POS)
    if use_pos:
        for p in (doc.payments or []):
            account = _get_payment_account(p.mode_of_payment, company)
            si.append("payments", {
                "mode_of_payment": p.mode_of_payment,
                "amount":          p.amount,
                "account":         account,
            })

    si.insert(ignore_permissions=True)

    if auto_submit:
        si.submit()

    return si


# ---------------------------------------------------------------------------
# Whitelisted helpers (called from JS)
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_target_school_class(student, target_academic_year):
    return predict_target_school_class(student, target_academic_year)


@frappe.whitelist()
def get_advance_period_options(academic_year, school_class, student=None):
    """Months of the target year the parent can pay with the renewal."""
    fee = 0.0
    if not (student and frappe.db.get_value("Student", student, "is_bolsista")):
        fee = flt(frappe.db.get_single_value("School Settings", "renewal_fee_amount"))
    return advance_months.get_options(academic_year, school_class, fee)


@frappe.whitelist()
def get_next_academic_year(academic_year):
    """
    Return the Academic Year whose start date falls immediately after
    the given year's end date (within a 90-day window).
    Returns None when not found.
    """
    end_date = frappe.db.get_value("Academic Year", academic_year, "end_date")
    if not end_date:
        return None

    next_start_min = add_days(end_date, 1)
    next_start_max = add_days(end_date, 90)

    result = frappe.db.sql(
        """SELECT name FROM `tabAcademic Year`
           WHERE start_date BETWEEN %s AND %s
           ORDER BY start_date ASC LIMIT 1""",
        (next_start_min, next_start_max),
        as_dict=True,
    )
    return result[0]["name"] if result else None


@frappe.whitelist()
def get_student_renewal_status(student):
    """
    Returns renewal status for the student relative to the current academic year
    and the configured renewal window. Used by the Student form actions modal.
    """
    settings = frappe.get_single("School Settings")
    period_start  = settings.get("renewal_period_start")
    period_end    = settings.get("renewal_period_end")
    current_year  = settings.get("current_academic_year")

    if not current_year:
        return None

    today_date = getdate(today())
    in_period = bool(
        period_start and period_end
        and getdate(period_start) <= today_date <= getdate(period_end)
    )

    next_year = get_next_academic_year(current_year)

    renewal = frappe.db.get_value(
        "Renovacao De Matricula",
        {
            "student":       student,
            "academic_year": current_year,
            "docstatus":     1,
        },
        ["name", "target_academic_year", "renewal_date"],
        as_dict=True,
    )

    return {
        "in_period":    in_period,
        "period_start": str(period_start) if period_start else None,
        "period_end":   str(period_end) if period_end else None,
        "current_year": current_year,
        "next_year":    next_year,
        "renewal":      renewal,
    }


@frappe.whitelist()
def get_student_renewal_history(student, limit=5):
    """
    Returns the last N renewals for a student plus current-window context.
    Used by the Student form renewal history panel.
    """
    settings = frappe.get_single("School Settings")
    period_start  = settings.get("renewal_period_start")
    period_end    = settings.get("renewal_period_end")
    current_year  = settings.get("current_academic_year")

    today_date = getdate(today())
    in_period = bool(
        period_start and period_end and current_year
        and getdate(period_start) <= today_date <= getdate(period_end)
    )

    next_year = get_next_academic_year(current_year) if current_year else None

    renewals = frappe.db.sql(
        """
        SELECT
            r.name,
            r.academic_year,
            r.target_academic_year,
            r.renewal_date,
            r.docstatus,
            r.sales_invoice
        FROM `tabRenovacao De Matricula` r
        WHERE r.student = %(student)s
          AND r.docstatus != 2
        ORDER BY r.renewal_date DESC
        LIMIT %(limit)s
        """,
        {"student": student, "limit": int(limit)},
        as_dict=True,
    )

    # Current-year renewal needed by the actions modal
    current_renewal = next(
        (r for r in renewals if r.academic_year == current_year and r.docstatus == 1),
        None,
    )

    return {
        "in_period":       in_period,
        "period_start":    str(period_start) if period_start else None,
        "period_end":      str(period_end) if period_end else None,
        "current_year":    current_year,
        "next_year":       next_year,
        "current_renewal": current_renewal,
        "renewals":        renewals,
    }
