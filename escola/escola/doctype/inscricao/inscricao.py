import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, getdate, today


class Inscricao(Document):
    def before_save(self):
        parts = [p for p in [self.first_name, self.last_name] if p]
        self.full_name = " ".join(parts)

    def validate(self):
        self._validate_guardian_requirement()
        self._validate_class_group()
        self._warn_possible_duplicate()

    def on_submit(self):
        guardian_name = self._get_or_create_guardian()
        self._create_student(guardian_name)
        self._create_sga()
        inv = _create_enrollment_invoice(self)
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

    def _validate_class_group(self):
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
                  "<b><a href='/app/student/{0}'>{0}</a></b>. "
                  "Verifique se não é um registo duplicado antes de continuar.").format(existing),
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
            "current_status": "Activo",
            "primary_guardian": guardian_name,
        })
        student.insert(ignore_permissions=True)
        self.db_set("student", student.name)

    def _create_sga(self):
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

    def _close_sga(self):
        if not self.student:
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


def _create_enrollment_invoice(doc):
    """Create a Sales Invoice for the enrollment fee. Returns the invoice or None."""
    from escola.escola.doctype.student.student import ensure_customer_for_student

    settings = frappe.get_single("School Settings")
    if not int(settings.get("auto_invoice_on_enrollment") or 0):
        return None

    item_code = settings.get("enrollment_fee_item_code")
    if not item_code:
        frappe.msgprint(
            _("Factura de inscrição não gerada: configure o <b>Item da Taxa de Inscrição</b> em Configurações da Escola."),
            title=_("Item em falta"),
            indicator="orange",
        )
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
    auto_submit = int(settings.get("auto_submit_enrollment_invoice") or 0)
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

    if is_pos and pos_profile:
        si.is_pos      = 1
        si.pos_profile = pos_profile

    try:
        si.escola_student = doc.student
    except Exception:
        pass

    si.append("items", {
        "item_code":   item_code,
        "item_name":   description,
        "description": description,
        "qty":         1,
        "rate":        fee_amount,
    })

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
def get_available_turmas(academic_year, school_class):
    """Return all active Class Groups for the given year + class with student counts."""
    return frappe.get_all(
        "Class Group",
        filters={"academic_year": academic_year, "school_class": school_class, "is_active": 1},
        fields=["name", "group_name", "student_count", "max_students", "shift"],
        order_by="group_name asc",
    )


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
