import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, today


@frappe.whitelist()
def get_student_academic_history(student):
    """Return academic history aggregated per academic year for the given student."""
    from collections import defaultdict

    # 1. Student Group Assignments → backbone (one slot per unique academic_year, most recent SGA wins)
    sgas = frappe.db.get_all(
        "Student Group Assignment",
        filters={"student": student},
        fields=["academic_year", "class_group", "school_class", "status", "assignment_date"],
        order_by="academic_year desc, assignment_date desc",
    )

    years = {}
    for sga in sgas:
        yr = sga.academic_year or "—"
        if yr not in years:
            years[yr] = {
                "academic_year": yr,
                "school_class": sga.school_class or "",
                "class_group": sga.class_group or "",
                "sga_status": sga.status or "",
                "assignment_date": frappe.utils.formatdate(sga.assignment_date) if sga.assignment_date else "",
                "final_decision": "",
                "overall_average": None,
                "total_absences": None,
                "report_card": None,
            }

    # 2. Report Cards → enrich with overall_average, final_decision, name
    rcs = frappe.db.get_all(
        "Report Card",
        filters={"student": student},
        fields=["name", "academic_year", "overall_average", "final_decision"],
    )
    for rc in rcs:
        yr = rc.academic_year or "—"
        if yr not in years:
            years[yr] = {
                "academic_year": yr,
                "school_class": "",
                "class_group": "",
                "sga_status": "",
                "assignment_date": "",
                "final_decision": "",
                "overall_average": None,
                "total_absences": None,
                "report_card": None,
            }
        years[yr]["report_card"] = rc.name
        years[yr]["final_decision"] = rc.final_decision or ""
        if rc.overall_average is not None:
            years[yr]["overall_average"] = float(rc.overall_average)

    # 3. Total absences from Annual Assessment Rows
    aa_rows = frappe.db.sql(
        """
        SELECT aa.academic_year, SUM(aar.total_absences) AS total_absences
        FROM `tabAnnual Assessment Row` aar
        JOIN `tabAnnual Assessment` aa ON aa.name = aar.parent
        WHERE aar.student = %s
        GROUP BY aa.academic_year
        """,
        student,
        as_dict=True,
    )
    for row in aa_rows:
        yr = row.academic_year or "—"
        if yr in years:
            years[yr]["total_absences"] = int(row.total_absences or 0)

    # 4. Fallback absences from Term Attendance Rows (years not already covered)
    missing = [yr for yr, d in years.items() if d["total_absences"] is None]
    if missing:
        ta_rows = frappe.db.sql(
            """
            SELECT ta.academic_year, SUM(tar.total_absences) AS total_absences
            FROM `tabTerm Attendance Row` tar
            JOIN `tabTerm Attendance` ta ON ta.name = tar.parent
            WHERE tar.student = %s
            GROUP BY ta.academic_year
            """,
            student,
            as_dict=True,
        )
        for row in ta_rows:
            yr = row.academic_year or "—"
            if yr in years and years[yr]["total_absences"] is None:
                years[yr]["total_absences"] = int(row.total_absences or 0)

    return sorted(years.values(), key=lambda x: x["academic_year"], reverse=True)


@frappe.whitelist()
def get_student_invoices(student):
    """Return all non-cancelled Sales Invoices for a student with summary totals."""
    from frappe.utils import getdate, today

    rows = frappe.db.sql(
        """
        SELECT
            si.name,
            si.posting_date,
            si.due_date,
            si.grand_total,
            si.outstanding_amount,
            si.docstatus,
            si.escola_mes_referencia,
            si.escola_billing_cycle,
            bc.billing_mode
        FROM `tabSales Invoice` si
        LEFT JOIN `tabBilling Cycle` bc ON bc.name = si.escola_billing_cycle
        WHERE si.escola_student = %s
          AND si.docstatus != 2
        ORDER BY si.posting_date DESC
        """,
        student,
        as_dict=True,
    )

    today_date = getdate(today())
    invoices = []
    for r in rows:
        paid = float(r.grand_total or 0) - float(r.outstanding_amount or 0)
        is_overdue = (
            r.docstatus == 1
            and float(r.outstanding_amount or 0) > 0
            and r.due_date
            and getdate(r.due_date) < today_date
        )
        if r.docstatus == 0:
            status = "Rascunho"
        elif float(r.outstanding_amount or 0) == 0:
            status = "Paga"
        elif is_overdue:
            status = "Em Atraso"
        else:
            status = "Emitida"

        invoices.append({
            "name":              r.name,
            "posting_date":      frappe.utils.formatdate(r.posting_date),
            "due_date":          frappe.utils.formatdate(r.due_date) if r.due_date else "—",
            "grand_total":       float(r.grand_total or 0),
            "outstanding":       float(r.outstanding_amount or 0),
            "paid":              round(paid, 2),
            "status":            status,
            "mes_referencia":    r.escola_mes_referencia or "—",
            "billing_mode":      r.billing_mode or "—",
            "billing_cycle":     r.escola_billing_cycle or "",
        })

    total_invoiced   = sum(i["grand_total"]  for i in invoices)
    total_paid       = sum(i["paid"]         for i in invoices)
    total_outstanding = sum(i["outstanding"] for i in invoices)

    return {
        "invoices": invoices,
        "summary": {
            "total_invoiced":    round(total_invoiced, 2),
            "total_paid":        round(total_paid, 2),
            "total_outstanding": round(total_outstanding, 2),
            "count":             len(invoices),
        },
    }


@frappe.whitelist()
def register_withdrawal(student, withdrawal_date, withdrawal_reason):
    """
    Mark a student as Desistente:
    1. Set current_status, withdrawal_date, withdrawal_reason on Student
    2. Close their active Student Group Assignment — roster removal,
       current-turma clearing, and draft-pauta cleanup are handled by the
       shared Student Group Assignment sync helpers (same as Troca de Turma
       and Student Transfer use).
    """
    from escola.escola.doctype.student_group_assignment.student_group_assignment import (
        _roster_sync, _sync_student_current_turma, _remove_from_draft_pautas,
    )

    frappe.db.set_value("Student", student, {
        "current_status":    "Desistente",
        "withdrawal_date":   frappe.utils.getdate(withdrawal_date),
        "withdrawal_reason": withdrawal_reason or "",
    })

    sga_name = frappe.db.get_value(
        "Student Group Assignment",
        {"student": student, "status": "Activa"},
        "name",
    )

    class_group = None
    if sga_name:
        frappe.db.set_value("Student Group Assignment", sga_name, "status", "Encerrada")
        sga = frappe.get_doc("Student Group Assignment", sga_name)
        class_group = sga.class_group
        _roster_sync(sga)
        _sync_student_current_turma(sga)
        _remove_from_draft_pautas(sga)

    frappe.db.commit()
    return {"class_group": class_group}


@frappe.whitelist()
def get_duplicate_removal_preview(student):
    """
    Summarize what deleting this student would remove, and whether it's
    blocked. Only ever safe for a pure registration duplicate with nothing
    officially recorded yet — refuses if anything submitted references the
    student (those must be cancelled manually, or the two students merged
    via Rename > Merge with existing instead).
    """
    blockers = []

    submitted_invoices = frappe.db.count("Sales Invoice", {"escola_student": student, "docstatus": 1})
    if submitted_invoices:
        blockers.append(_("{0} factura(s) submetida(s)").format(submitted_invoices))

    submitted_grades = frappe.db.sql(
        """
        SELECT COUNT(*) FROM `tabGrade Entry Row` ger
        JOIN `tabGrade Entry` ge ON ge.name = ger.parent
        WHERE ger.student = %s AND ge.docstatus = 1
        """,
        student,
    )[0][0]
    if submitted_grades:
        blockers.append(_("{0} nota(s) submetida(s) em pauta").format(submitted_grades))

    submitted_attendance = frappe.db.sql(
        """
        SELECT COUNT(*) FROM `tabTerm Attendance Row` tar
        JOIN `tabTerm Attendance` ta ON ta.name = tar.parent
        WHERE tar.student = %s AND ta.docstatus = 1
        """,
        student,
    )[0][0]
    if submitted_attendance:
        blockers.append(_("{0} registo(s) de frequência submetido(s)").format(submitted_attendance))

    for dt in ("Adiantamento De Pagamento", "Renovacao De Matricula", "Troca De Turma", "Student Transfer"):
        cnt = frappe.db.count(dt, {"student": student, "docstatus": 1})
        if cnt:
            blockers.append(_("{0} {1} submetida(s)").format(cnt, dt))

    return {
        "blocked": bool(blockers),
        "blockers": blockers,
        "draft_invoices": frappe.db.count("Sales Invoice", {"escola_student": student, "docstatus": 0}),
        "assignments": frappe.db.count("Student Group Assignment", {"student": student}),
        "has_customer": bool(frappe.db.get_value("Customer", {"escola_student": student}, "name")),
    }


@frappe.whitelist()
def delete_duplicate_student(student):
    """
    Permanently remove a Student created by mistake (e.g. a typo'd duplicate
    registration), along with everything tied only to it in draft state:
    draft invoices, Student Group Assignments (and their roster rows, via
    on_trash), draft grade-entry/attendance rows, draft
    Adiantamento/Renovação/Troca/Transfer docs, and its auto-created
    Customer. Refuses if anything submitted references the student — see
    get_duplicate_removal_preview. Not for merging two real students'
    histories; use Rename > Merge with existing for that instead.
    """
    preview = get_duplicate_removal_preview(student)
    if preview["blocked"]:
        frappe.throw(
            _("Não é possível eliminar: existem registos submetidos ligados a este aluno "
              "({0}). Cancele-os manualmente primeiro, ou utilize Renomear > "
              "Juntar com Existente para fundir com o registo correcto.").format(
                ", ".join(preview["blockers"])
            ),
            title=_("Eliminação bloqueada"),
        )

    deleted = {"invoices": 0, "assignments": 0, "grade_rows": 0, "attendance_rows": 0, "related_docs": 0}

    for name in frappe.get_all("Sales Invoice", filters={"escola_student": student, "docstatus": 0}, pluck="name"):
        frappe.delete_doc("Sales Invoice", name, ignore_permissions=True)
        deleted["invoices"] += 1

    for dt in ("Adiantamento De Pagamento", "Renovacao De Matricula", "Troca De Turma", "Student Transfer"):
        for name in frappe.get_all(dt, filters={"student": student, "docstatus": 0}, pluck="name"):
            frappe.delete_doc(dt, name, ignore_permissions=True)
            deleted["related_docs"] += 1

    for name in frappe.get_all("Student Group Assignment", filters={"student": student}, pluck="name"):
        frappe.delete_doc("Student Group Assignment", name, ignore_permissions=True)
        deleted["assignments"] += 1

    for row in frappe.db.sql(
        """
        SELECT ger.name FROM `tabGrade Entry Row` ger
        JOIN `tabGrade Entry` ge ON ge.name = ger.parent
        WHERE ger.student = %s AND ge.docstatus = 0
        """,
        student, as_dict=True,
    ):
        frappe.db.delete("Grade Entry Row", {"name": row.name})
        deleted["grade_rows"] += 1

    for row in frappe.db.sql(
        """
        SELECT tar.name FROM `tabTerm Attendance Row` tar
        JOIN `tabTerm Attendance` ta ON ta.name = tar.parent
        WHERE tar.student = %s AND ta.docstatus = 0
        """,
        student, as_dict=True,
    ):
        frappe.db.delete("Term Attendance Row", {"name": row.name})
        deleted["attendance_rows"] += 1

    customer = frappe.db.get_value("Customer", {"escola_student": student}, "name")
    if customer:
        frappe.delete_doc("Customer", customer, ignore_permissions=True)

    frappe.delete_doc("Student", student, ignore_permissions=True)
    frappe.db.commit()

    return deleted


def _calc_age(date_of_birth):
    if not date_of_birth:
        return None
    dob = getdate(date_of_birth)
    tod = getdate(today())
    age = tod.year - dob.year - ((tod.month, tod.day) < (dob.month, dob.day))
    return age if age >= 0 else None


def update_all_student_ages():
    """Daily scheduler job — recalculates idade for every student with a date_of_birth."""
    rows = frappe.db.get_all(
        "Student",
        filters=[["date_of_birth", "is", "set"]],
        fields=["name", "date_of_birth"],
    )
    for row in rows:
        age = _calc_age(row.date_of_birth)
        if age is not None:
            frappe.db.set_value("Student", row.name, "idade", age, update_modified=False)
    if rows:
        frappe.db.commit()


class Student(Document):
    def before_delete(self):
        active = frappe.db.count(
            "Student Group Assignment",
            {"student": self.name, "status": "Activa"},
        )
        if active:
            frappe.throw(
                _("Não é possível eliminar o aluno <b>{0}</b> porque tem <b>{1}</b> alocação(ões) activa(s). "
                  "Encerre todas as alocações antes de eliminar.").format(self.name, active),
                title=_("Aluno com alocações activas"),
            )
        invoices = frappe.db.count(
            "Sales Invoice",
            {"escola_student": self.name, "docstatus": 1},
        )
        if invoices:
            frappe.throw(
                _("Não é possível eliminar o aluno <b>{0}</b> porque tem <b>{1}</b> factura(s) submetida(s). "
                  "Cancele as facturas antes de eliminar.").format(self.name, invoices),
                title=_("Aluno com facturas"),
            )

    def before_insert(self):
        self._sync_full_name()
        self._generate_student_code()

    def before_rename(self, old, new, merge=False):
        # autoname is "field:full_name" — the Rename dialog has no manual
        # "New Name" input for that (Frappe expects the field to drive it),
        # so the document's own current full_name IS the target name here.
        return self.full_name

    def after_insert(self):
        try:
            ensure_customer_for_student(self.name)
        except Exception:
            pass  # never block student creation

    def before_save(self):
        self._sync_full_name()
        self.idade = _calc_age(self.date_of_birth)
        if not self.current_status:
            self.current_status = "Activo"
        self.pending_required_docs = sum(
            1 for row in (self.documents or [])
            if row.is_required and row.status == "Pendente"
        )

    def _sync_full_name(self):
        parts = filter(None, [self.first_name, self.last_name])
        self.full_name = " ".join(parts)

    def _generate_student_code(self):
        if self.student_code:
            return
        last = frappe.db.sql(
            "SELECT student_code FROM `tabStudent` "
            "WHERE student_code LIKE 'ALU-%' "
            "ORDER BY student_code DESC LIMIT 1"
        )
        if last and last[0][0]:
            try:
                seq = int(last[0][0].split("-")[1]) + 1
            except (IndexError, ValueError):
                seq = 1
        else:
            seq = 1
        self.student_code = "ALU-{:05d}".format(seq)


# ---------------------------------------------------------------------------
# Customer provisioning
# ---------------------------------------------------------------------------

def ensure_customer_for_student(student_name):
    """
    Return the ERPNext Customer linked to this student, creating one if needed.
    Safe to call multiple times — never creates duplicates.
    """
    try:
        existing = frappe.db.get_value("Customer", {"escola_student": student_name}, "name")
        if existing:
            return existing
    except Exception:
        pass

    student = (
        frappe.db.get_value("Student", student_name, ["full_name", "student_code"], as_dict=True)
        or frappe._dict()
    )
    full_name = student.get("full_name") or student_name

    customer = frappe.new_doc("Customer")
    customer.customer_name = full_name
    customer.customer_type = "Individual"
    customer.customer_group = (
        frappe.db.get_single_value("School Settings", "default_customer_group")
        or frappe.db.get_single_value("Selling Settings", "customer_group")
        or "All Customer Groups"
    )
    customer.territory = (
        frappe.db.get_single_value("School Settings", "default_territory")
        or frappe.db.get_single_value("Selling Settings", "territory")
        or "All Territories"
    )

    try:
        customer.escola_student = student_name
    except Exception:
        pass

    customer.insert(ignore_permissions=True)
    return customer.name


# ---------------------------------------------------------------------------
# Document management
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_student_documents(student):
    """Return document rows enriched with the Tipo de Documento label."""
    rows = frappe.get_all(
        "Student Document",
        filters={"parent": student},
        fields=["name", "document_type", "is_required", "status", "file", "submitted_date", "origin_enrollment", "notes"],
        order_by="is_required desc, document_type asc",
    )
    label_map = {}
    for row in rows:
        if row.document_type not in label_map:
            label_map[row.document_type] = (
                frappe.db.get_value("Tipo de Documento", row.document_type, "label") or row.document_type
            )
        row["document_label"] = label_map[row.document_type]
    return rows


@frappe.whitelist()
def mark_document_delivered(student, row_name, file_url=None, notes=None):
    """Set a Student Document row to Entregue, optionally attaching a file."""
    doc = frappe.get_doc("Student", student)
    for row in doc.documents:
        if row.name == row_name:
            row.status = "Entregue"
            row.submitted_date = today()
            if file_url:
                row.file = file_url
            if notes:
                row.notes = notes
            break
    doc.save(ignore_permissions=True)
    return True


@frappe.whitelist()
def reset_document_status(student, row_name):
    """Reset a Student Document row back to Pendente."""
    doc = frappe.get_doc("Student", student)
    for row in doc.documents:
        if row.name == row_name:
            row.status = "Pendente"
            row.submitted_date = None
            break
    doc.save(ignore_permissions=True)
    return True


@frappe.whitelist()
def add_student_document(student, document_type, status, file_url=None, notes=None):
    """Append a new document row to a Student record."""
    doc = frappe.get_doc("Student", student)
    already = any(r.document_type == document_type for r in doc.documents)
    if already:
        frappe.throw(
            _("O documento <b>{0}</b> já está registado para este aluno.").format(document_type),
            title=_("Documento duplicado"),
        )
    is_required = frappe.db.get_value("Tipo de Documento", document_type, "is_required") or 0
    doc.append("documents", {
        "document_type":    document_type,
        "is_required":      is_required,
        "status":           status or "Pendente",
        "submitted_date":   today() if status == "Entregue" else None,
        "file":             file_url or "",
        "notes":            notes or "",
    })
    doc.save(ignore_permissions=True)
    return True
