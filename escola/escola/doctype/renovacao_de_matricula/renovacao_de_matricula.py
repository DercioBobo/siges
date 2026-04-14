import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, getdate, today


# ---------------------------------------------------------------------------
# Document class
# ---------------------------------------------------------------------------

class RenovacaoDeMatricula(Document):

    def validate(self):
        self._validate_years()
        self._validate_not_duplicate()

    def on_submit(self):
        inv = _create_renewal_invoice(self)
        if inv:
            self.db_set("sales_invoice", inv.name)
            frappe.msgprint(
                _("Renovação confirmada. Factura <b><a href='/app/sales-invoice/{0}'>{0}</a></b> criada.").format(inv.name),
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
        if self.sales_invoice:
            inv_status = frappe.db.get_value("Sales Invoice", self.sales_invoice, "docstatus")
            if inv_status == 0:
                # Draft — safe to delete
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

    # ------------------------------------------------------------------

    def _validate_years(self):
        if self.academic_year and self.target_academic_year:
            if self.academic_year == self.target_academic_year:
                frappe.throw(
                    _("O Ano Lectivo de Renovação deve ser diferente do Ano Lectivo de Origem."),
                    title=_("Anos lectivos inválidos"),
                )

    def _validate_not_duplicate(self):
        existing = frappe.db.get_value(
            "Renovacao De Matricula",
            {
                "student":               self.student,
                "academic_year":         self.academic_year,
                "target_academic_year":  self.target_academic_year,
                "docstatus":             ("!=", 2),   # not cancelled
                "name":                  ("!=", self.name),
            },
            "name",
        )
        if existing:
            frappe.throw(
                _(
                    "Já existe uma Renovação de Matrícula para o aluno <b>{0}</b> "
                    "neste percurso de anos: <b><a href='/app/renovacao-de-matricula/{1}'>{1}</a></b>."
                ).format(self.student, existing),
                title=_("Renovação duplicada"),
            )


# ---------------------------------------------------------------------------
# Invoice creation helper
# ---------------------------------------------------------------------------

def _create_renewal_invoice(doc):
    """Create a Sales Invoice for the renewal fee. Returns the invoice or None."""
    from escola.escola.doctype.student.student import ensure_customer_for_student

    settings = frappe.get_single("School Settings")
    item_code = settings.get("renewal_fee_item_code")
    if not item_code:
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
    due_days   = int(frappe.db.get_single_value("School Settings", "invoice_due_days") or 30)
    today_date = today()
    due_date   = add_days(today_date, due_days)
    auto_submit = int(frappe.db.get_single_value("School Settings", "auto_submit_invoices") or 0)
    fee_amount  = float(settings.get("renewal_fee_amount") or 0)
    description = _("Renovação de Matrícula {0}").format(doc.target_academic_year)

    si = frappe.new_doc("Sales Invoice")
    si.customer     = customer
    si.company      = company
    si.posting_date = today_date
    si.due_date     = due_date
    si.remarks      = description

    try:
        si.escola_student = doc.student
    except Exception:
        pass

    si.append("items", {
        "item_code":  item_code,
        "item_name":  description,
        "description": description,
        "qty":        1,
        "rate":       fee_amount,
    })

    si.insert(ignore_permissions=True)
    if auto_submit:
        si.submit()

    return si


# ---------------------------------------------------------------------------
# Whitelisted helpers (called from JS)
# ---------------------------------------------------------------------------

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
    Returns renovation status for the student only when today is within the
    configured renewal period in School Settings. Returns None otherwise.

    Used by the Student form to show/hide the renewal badge.
    """
    settings = frappe.get_single("School Settings")
    period_start  = settings.get("renewal_period_start")
    period_end    = settings.get("renewal_period_end")
    current_year  = settings.get("current_academic_year")

    if not period_start or not period_end or not current_year:
        return None

    today_date = getdate(today())
    if not (getdate(period_start) <= today_date <= getdate(period_end)):
        return None

    # Find the next year for the current year
    next_year = get_next_academic_year(current_year)

    # Check if this student already has a submitted renewal
    renewal = frappe.db.get_value(
        "Renovacao De Matricula",
        {
            "student":              student,
            "academic_year":        current_year,
            "docstatus":            1,   # submitted
        },
        ["name", "target_academic_year", "renewal_date"],
        as_dict=True,
    )

    return {
        "in_period":        True,
        "period_start":     str(period_start),
        "period_end":       str(period_end),
        "current_year":     current_year,
        "next_year":        next_year,
        "renewal":          renewal,  # None or {name, target_academic_year, renewal_date}
    }
