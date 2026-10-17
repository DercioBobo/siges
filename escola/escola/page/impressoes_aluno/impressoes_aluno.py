"""
Impressões do Aluno — one place to print anything about a student.

get_hub() feeds the page (student card + the lists behind the Boletim,
Recibos and Facturas tiles); get_document_data() feeds the documents laid
out client-side (Declaração de Matrícula, Ficha do Aluno). The Extrato reuses
invoice_query.get_student_statement. Financial lists are only returned to
users who can read Sales Invoice (e.g. not Diretor Pedagógico).
"""

import frappe
from frappe import _

SCHOOL_FIELDS = ["school_name", "school_logo", "school_nif", "school_phone", "school_email", "school_address"]


def _can_see_finance():
    return bool(frappe.has_permission("Sales Invoice", "read"))


def _student_header(student):
    frappe.has_permission("Student", "read", doc=student, throw=True)
    st = frappe.db.get_value(
        "Student", student,
        ["name", "full_name", "student_code", "current_status", "financial_status",
         "current_school_class", "current_class_group", "primary_guardian", "gender",
         "date_of_birth", "is_bolsista"],
        as_dict=True,
    )
    if not st:
        frappe.throw(_("Aluno {0} não encontrado.").format(student))
    st.class_name = (frappe.db.get_value("School Class", st.current_school_class, "class_name")
                     if st.current_school_class else None)
    st.turma_name = (frappe.db.get_value("Class Group", st.current_class_group, "group_name")
                     if st.current_class_group else None)
    return st


@frappe.whitelist()
def get_hub(student):
    st = _student_header(student)
    finance = _can_see_finance()

    report_cards = frappe.get_all(
        "Report Card",
        filters={"student": student},
        fields=["name", "academic_year", "school_class", "class_group", "overall_average", "final_decision"],
        order_by="academic_year desc",
    )

    invoices, payments = [], []
    if finance:
        from escola.escola.invoice_query import _invoice_payments, _invoice_types

        invoices = frappe.get_all(
            "Sales Invoice",
            filters={"escola_student": student, "docstatus": ["!=", 2]},
            fields=["name", "posting_date", "grand_total", "outstanding_amount", "docstatus"],
            order_by="posting_date desc",
        )
        types = _invoice_types([i.name for i in invoices])
        for i in invoices:
            i.tipo = types.get(i.name, _("Outro"))
        payments = _invoice_payments([i.name for i in invoices]) if invoices else []

    return {
        "student": st,
        "can_see_finance": finance,
        "report_cards": report_cards,
        "invoices": invoices,
        "payments": payments,
    }


@frappe.whitelist()
def get_document_data(student):
    """Everything the Declaração de Matrícula and the Ficha do Aluno print."""
    from escola.escola.doctype.student.student import get_student_academic_history, get_student_documents

    st = _student_header(student)
    st.update(frappe.db.get_value(
        "Student", student,
        ["first_name", "last_name", "place_of_birth", "idade", "phone", "address",
         "bi_number", "admission_date", "withdrawal_date", "return_date"],
        as_dict=True,
    ))

    # Current enrolment = the active turma assignment, if any
    sga = frappe.db.get_value(
        "Student Group Assignment", {"student": student, "status": "Activa"},
        ["academic_year", "school_class", "class_group", "assignment_date"],
        as_dict=True, order_by="creation desc",
    )
    if sga:
        sga.class_name = frappe.db.get_value("School Class", sga.school_class, "class_name") or sga.school_class
        sga.turma_name = frappe.db.get_value("Class Group", sga.class_group, "group_name") or sga.class_group

    guardian = None
    if st.primary_guardian:
        guardian = frappe.db.get_value(
            "Guardian", st.primary_guardian,
            ["full_name", "relationship", "phone", "alternative_phone", "email", "address"],
            as_dict=True,
        )

    return {
        "school": frappe.db.get_value("School Settings", "School Settings", SCHOOL_FIELDS, as_dict=True),
        "student": st,
        "enrolment": sga,
        "guardian": guardian,
        "history": get_student_academic_history(student),
        "documents": get_student_documents(student),
    }
