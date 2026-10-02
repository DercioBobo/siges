import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, flt, getdate, today

from escola.escola import advance_months


class Inscricao(Document):
    def before_save(self):
        parts = [p for p in [self.first_name, self.last_name] if p]
        self.full_name = " ".join(parts)

    def validate(self):
        self._validate_guardian_requirement()
        self._validate_class_group()
        self._warn_possible_duplicate()
        advance_months.compute_totals(
            self, self.academic_year, self.school_class,
            _enrollment_fee_amount(self), exempt=self.is_bolsista,
        )
        self._validate_payment_total()

    def before_submit(self):
        self._require_turma_decision()

    def on_submit(self):
        guardian_name = self._get_or_create_guardian()
        self._create_student(guardian_name)
        self._create_sga()
        self._seed_student_documents()
        adp = advance_months.create_adiantamento(self, self.student, self.academic_year, self.school_class)
        inv = _create_enrollment_invoice(self, adp)
        if adp:
            advance_months.submit_adiantamento(self, adp, inv)
        if inv:
            self.db_set("sales_invoice", inv.name)
            from escola.escola.invoice_utils import invoice_success_msg
            frappe.msgprint(
                invoice_success_msg(inv.name, _("Matrícula confirmada.")),
                title=_("Matrícula concluída"),
                indicator="green",
            )

    def on_cancel(self):
        self._close_sga()
        advance_months.cancel_adiantamento(self)
        if self.sales_invoice:
            inv_status = frappe.db.get_value("Sales Invoice", self.sales_invoice, "docstatus")
            if inv_status == 0:
                frappe.delete_doc("Sales Invoice", self.sales_invoice, ignore_permissions=True)
                self.db_set("sales_invoice", None)
                frappe.msgprint(_("Factura de inscrição eliminada."), indicator="orange")
            elif inv_status == 1:
                frappe.msgprint(
                    _("A factura <b>{0}</b> já está submetida. Cancele-a manualmente se necessário.").format(
                        self.sales_invoice
                    ),
                    title=_("Factura não cancelada"),
                    indicator="orange",
                )

    # ------------------------------------------------------------------

    def _validate_guardian_requirement(self):
        if self.guardian or self.guardian_first_name:
            return
        requires = frappe.db.get_single_value("School Settings", "enrollment_requires_guardian")
        if requires:
            frappe.throw(
                _("As Configurações da Escola exigem um Encarregado de Educação na matrícula. "
                  "Seleccione um Encarregado existente ou preencha os dados do novo Encarregado."),
                title=_("Encarregado obrigatório"),
            )

    def _require_turma_decision(self):
        """Leaving the student without a turma must be an explicit choice, not an oversight."""
        if self.class_group or self.skip_turma:
            return
        frappe.throw(
            _("Seleccione uma Turma, crie uma <b>Nova Turma</b>, ou escolha <b>Não alocar</b> "
              "para deixar o aluno como Pendente de Turma."),
            title=_("Turma por definir"),
        )

    def _validate_class_group(self):
        if self.class_group:
            self.skip_turma = 0
        if not self.class_group:
            return
        cg = frappe.db.get_value(
            "Class Group",
            self.class_group,
            ["academic_year", "school_class", "is_active"],
            as_dict=True,
        )
        if not cg:
            return
        if cg.academic_year != self.academic_year:
            frappe.throw(
                _("A Turma <b>{0}</b> pertence ao Ano Lectivo <b>{1}</b>, "
                  "não ao Ano Lectivo <b>{2}</b>.").format(
                    self.class_group, cg.academic_year, self.academic_year
                ),
                title=_("Turma incompatível"),
            )
        if self.school_class and cg.school_class != self.school_class:
            frappe.throw(
                _("A Turma <b>{0}</b> pertence à Classe <b>{1}</b>, "
                  "não à Classe <b>{2}</b>.").format(
                    self.class_group, cg.school_class, self.school_class
                ),
                title=_("Classe incompatível"),
            )
        if not cg.is_active:
            frappe.throw(
                _("A Turma <b>{0}</b> não está activa.").format(self.class_group),
                title=_("Turma inactiva"),
            )

    def _validate_payment_total(self):
        """With months paid upfront, the payments must cover the whole invoice."""
        if not self.advance_periods or not self.payments:
            return
        paid = sum(flt(p.amount) for p in self.payments)
        if abs(paid - flt(self.total_to_pay)) > 0.01:
            frappe.throw(
                _("O total dos métodos de pagamento ({0}) não corresponde ao Total a Pagar ({1}).").format(
                    frappe.format_value(paid, {"fieldtype": "Currency"}),
                    frappe.format_value(self.total_to_pay, {"fieldtype": "Currency"}),
                ),
                title=_("Pagamento incorrecto"),
            )

    def _warn_possible_duplicate(self):
        if not (self.first_name and self.last_name and self.date_of_birth):
            return
        existing = frappe.db.get_value(
            "Student",
            {
                "first_name": self.first_name,
                "last_name": self.last_name,
                "date_of_birth": getdate(self.date_of_birth),
            },
            "name",
        )
        if existing:
            frappe.msgprint(
                _("Atenção: já existe um aluno com o mesmo nome e data de nascimento: "
                  "<b><a href='/app/student/{0}'>{1} ({0})</a></b>. "
                  "Verifique se não é um registo duplicado antes de continuar.").format(
                    existing, frappe.utils.escape_html(self.first_name + " " + self.last_name)
                ),
                title=_("Possível duplicado"),
                indicator="orange",
            )

    # ------------------------------------------------------------------

    def _get_or_create_guardian(self):
        if self.guardian:
            return self.guardian
        if not self.guardian_first_name:
            return None
        g = frappe.get_doc({
            "doctype": "Guardian",
            "first_name": self.guardian_first_name,
            "last_name": self.guardian_last_name or "",
            "relationship": self.guardian_relationship or "",
            "phone": self.guardian_phone or "",
            "email": self.guardian_email or "",
            "is_active": 1,
        })
        g.insert(ignore_permissions=True)
        self.db_set("guardian_created", g.name)
        return g.name

    def _create_student(self, guardian_name):
        status = "Activo" if self.class_group else "Pendente de Turma"
        student = frappe.get_doc({
            "doctype": "Student",
            "first_name": self.first_name,
            "last_name": self.last_name,
            "gender": self.gender,
            "date_of_birth": self.date_of_birth,
            "place_of_birth": self.place_of_birth or "",
            "phone": self.phone or "",
            "address": self.address or "",
            "admission_date": self.enrollment_date,
            "current_status": status,
            "current_school_class": self.school_class or "",
            "primary_guardian": guardian_name,
            "is_bolsista": self.is_bolsista or 0,
        })
        student.insert(ignore_permissions=True)
        self.db_set("student", student.name)

    def _create_sga(self):
        if not self.class_group:
            return  # no turma yet — student stays Pendente de Turma
        frappe.get_doc({
            "doctype": "Student Group Assignment",
            "student": self.student,
            "class_group": self.class_group,
            "academic_year": self.academic_year,
            "school_class": self.school_class,
            "assignment_date": self.enrollment_date,
            "status": "Activa",
            "notes": _("Criado automaticamente pela Inscrição {0}.").format(self.name),
        }).insert(ignore_permissions=True)

    def _seed_student_documents(self):
        """Populate Student.documents with required document types for this enrollment_type."""
        if not self.student:
            return
        enrollment_type = self.enrollment_type or "Novo"
        doc_types = frappe.get_all(
            "Tipo de Documento",
            filters={"is_active": 1, "applies_to": ["in", ["Ambos", enrollment_type]]},
            fields=["name", "is_required"],
            order_by="is_required desc, name asc",
        )
        if not doc_types:
            return

        # Collect any files the secretary pre-uploaded on the Inscricao form
        preview_files = {
            row.document_type: row.file
            for row in (self.doc_previews or [])
            if row.document_type and row.file
        }

        student_doc = frappe.get_doc("Student", self.student)
        existing_types = {row.document_type for row in (student_doc.documents or [])}
        added = False
        for dt in doc_types:
            if dt.name not in existing_types:
                file_url = preview_files.get(dt.name)
                student_doc.append("documents", {
                    "document_type": dt.name,
                    "is_required": dt.is_required,
                    "status": "Entregue" if file_url else "Pendente",
                    "submitted_date": frappe.utils.today() if file_url else None,
                    "file": file_url or "",
                    "origin_enrollment": self.name,
                })
                added = True
        if added:
            student_doc.save(ignore_permissions=True)

    def _close_sga(self):
        if not self.student or not self.class_group:
            return
        sga_name = frappe.db.get_value(
            "Student Group Assignment",
            {"student": self.student, "class_group": self.class_group, "status": "Activa"},
            "name",
        )
        if sga_name:
            sga = frappe.get_doc("Student Group Assignment", sga_name)
            sga.status = "Encerrada"
            sga.save(ignore_permissions=True)


def _enrollment_fee_amount(doc):
    """Enrolment fee that will be invoiced for this Inscrição (0 when none)."""
    if doc.is_bolsista:
        return 0.0
    settings = frappe.get_single("School Settings")
    if not int(settings.get("auto_invoice_on_enrollment") or 0) or not settings.get("enrollment_fee_item_code"):
        return 0.0
    return flt(settings.get("enrollment_fee_amount"))


def _create_enrollment_invoice(doc, adp=None):
    """Create one Sales Invoice for the enrolment fee plus any months paid upfront
    (``adp``, the Adiantamento recording them). Returns the invoice or None."""
    from escola.escola.doctype.student.student import ensure_customer_for_student

    settings = frappe.get_single("School Settings")
    bill_fee = (
        int(settings.get("auto_invoice_on_enrollment") or 0)
        and not frappe.db.get_value("Student", doc.student, "is_bolsista")
    )
    item_code = settings.get("enrollment_fee_item_code")
    if bill_fee and not item_code:
        frappe.msgprint(
            _("Factura de inscrição não gerada: configure o <b>Item da Taxa de Inscrição</b> em Configurações da Escola."),
            title=_("Item em falta"),
            indicator="orange",
        )
        bill_fee = False

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
    # Months paid upfront are paid by definition — always submit those invoices.
    auto_submit = int(settings.get("auto_submit_enrollment_invoice") or 0) or bool(adp)
    fee_amount  = float(settings.get("enrollment_fee_amount") or 0)
    is_pos      = int(settings.get("enrollment_is_pos") or 0)
    pos_profile = settings.get("enrollment_pos_profile") or ""
    description = _("Taxa de Inscrição — {0}").format(doc.academic_year or "")

    si = frappe.new_doc("Sales Invoice")
    si.customer     = customer
    si.company      = company
    si.posting_date = today_date
    si.due_date     = due_date
    si.remarks      = description
    if adp:
        si.remarks = _("Inscrição {0} — {1} mensalidade(s)").format(doc.academic_year or "", adp.total_periods)

    if is_pos and pos_profile:
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

    if is_pos:
        for p in (doc.payments or []):
            account = frappe.db.get_value(
                "Mode of Payment Account",
                {"parent": p.mode_of_payment, "company": company},
                "default_account",
            )
            si.append("payments", {
                "mode_of_payment": p.mode_of_payment,
                "amount":          p.amount,
                "account":         account,
            })

    si.insert(ignore_permissions=True)
    if auto_submit:
        si.submit()

    return si


@frappe.whitelist()
def get_advance_period_options(academic_year, school_class):
    """Months the parent can pay at enrolment, plus what the form needs to price them."""
    return advance_months.get_options(
        academic_year, school_class, _enrollment_fee_amount(frappe._dict(is_bolsista=0))
    )


@frappe.whitelist()
def get_required_docs_for_type(enrollment_type):
    """Return active Tipo de Documento records that apply to the given enrollment_type."""
    return frappe.get_all(
        "Tipo de Documento",
        filters={"is_active": 1, "applies_to": ["in", ["Ambos", enrollment_type]]},
        fields=["name", "label", "is_required", "description"],
        order_by="is_required desc, label asc",
    )


@frappe.whitelist()
def get_available_turmas(academic_year, school_class):
    """Return all active Class Groups for the given year + class with student counts."""
    return frappe.get_all(
        "Class Group",
        filters={"academic_year": academic_year, "school_class": school_class, "is_active": 1},
        fields=["name", "group_name", "student_count", "max_students", "shift"],
        order_by="group_name asc",
    )


def _next_turma_name(academic_year, school_class):
    """Next free '{class_name} {letter}-{YY}' name, skipping letters already taken."""
    from escola.escola.doctype.student_promotion.student_promotion import _turma_name

    n_existing = frappe.db.count(
        "Class Group", {"academic_year": academic_year, "school_class": school_class}
    )
    for offset in range(26):
        name = _turma_name(school_class, academic_year, n_existing, offset)
        if not frappe.db.exists("Class Group", {"group_name": name, "academic_year": academic_year}):
            return name
    return _turma_name(school_class, academic_year, n_existing)


@frappe.whitelist()
def get_new_turma_defaults(academic_year, school_class):
    """Pre-fill values for the 'Nova Turma' dialog on the Inscrição form."""
    return {
        "group_name": _next_turma_name(academic_year, school_class),
        "max_students": frappe.db.get_single_value("School Settings", "default_max_students_per_class") or 0,
    }


@frappe.whitelist()
def create_turma(academic_year, school_class, group_name, shift=None, max_students=0, classroom=None):
    """Create a Class Group from the Inscrição form so the secretary never leaves the enrolment."""
    group_name = (group_name or "").strip()
    if not group_name:
        frappe.throw(_("Indique o nome da Turma."), title=_("Nome em falta"))
    if frappe.db.exists("Class Group", {"group_name": group_name, "academic_year": academic_year}):
        frappe.throw(
            _("Já existe uma Turma <b>{0}</b> no Ano Lectivo <b>{1}</b>.").format(group_name, academic_year),
            title=_("Turma duplicada"),
        )

    cg = frappe.get_doc({
        "doctype": "Class Group",
        "group_name": group_name,
        "academic_year": academic_year,
        "school_class": school_class,
        "shift": shift or "",
        "classroom": classroom or "",
        "max_students": int(max_students or 0),
        "is_active": 1,
        "student_count": 0,
    }).insert()  # respects Class Group create permission
    return cg.name


@frappe.whitelist()
def reactivate_student(student_name, class_group_name):
    """
    Reactivate a student who previously left (Transferido or Desistente).
    Sets current_status back to Activo and creates a new SGA.
    """
    student = frappe.get_doc("Student", student_name)
    if student.current_status not in ("Transferido", "Desistente"):
        frappe.throw(
            _("O aluno <b>{0}</b> não está como Transferido ou Desistente. "
              "Estado actual: <b>{1}</b>.").format(student_name, student.current_status),
            title=_("Reactivação inválida"),
        )

    # Check no active SGA already
    cg = frappe.db.get_value(
        "Class Group", class_group_name,
        ["academic_year", "school_class"], as_dict=True
    )
    if frappe.db.exists("Student Group Assignment", {
        "student": student_name,
        "academic_year": cg.academic_year,
        "status": "Activa",
    }):
        frappe.throw(
            _("O aluno já tem uma alocação activa para o Ano Lectivo <b>{0}</b>.").format(
                cg.academic_year
            ),
            title=_("Alocação já existente"),
        )

    frappe.db.set_value("Student", student_name, "current_status", "Activo", update_modified=False)

    sga = frappe.get_doc({
        "doctype": "Student Group Assignment",
        "student": student_name,
        "class_group": class_group_name,
        "academic_year": cg.academic_year,
        "school_class": cg.school_class,
        "assignment_date": frappe.utils.today(),
        "status": "Activa",
        "notes": _("Reactivação manual."),
    })
    sga.insert()
    frappe.db.commit()
    return sga.name
