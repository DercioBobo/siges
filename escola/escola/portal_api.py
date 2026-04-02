"""
escola/portal_api.py

Whitelisted API endpoints for the Guardian Portal.
Trust chain: frappe.session.user → Guardian (user_id) → Student (primary_guardian)
Every endpoint validates this chain before returning any data.
"""
import frappe
from frappe import _
from frappe.utils.password import check_password, update_password


# ---------------------------------------------------------------------------
# Internal auth helpers
# ---------------------------------------------------------------------------

def _get_guardian():
    """
    Validate portal access for the current session and return the Guardian doc as a dict.
    Raises PermissionError on any failure so the caller never needs to check return value.
    """
    if not frappe.db.get_single_value("School Settings", "guardian_portal_enabled"):
        frappe.throw(_("O portal do encarregado está temporariamente desactivado."), frappe.PermissionError)

    user = frappe.session.user
    if not user or user == "Guest":
        frappe.throw(_("Sessão inválida. Por favor inicie sessão novamente."), frappe.AuthenticationError)

    guardian = frappe.db.get_value(
        "Guardian",
        {"user_id": user},
        ["name", "full_name", "portal_access", "phone", "alternative_phone", "email", "address"],
        as_dict=True,
    )
    if not guardian:
        frappe.throw(_("Nenhum encarregado associado a este utilizador."), frappe.PermissionError)
    if not guardian.portal_access:
        frappe.throw(_("O acesso ao portal foi desactivado para este encarregado."), frappe.PermissionError)

    return guardian


def _assert_owns_student(guardian_name, student_name):
    """Raise PermissionError if student's primary_guardian does not match."""
    owner = frappe.db.get_value("Student", student_name, "primary_guardian")
    if owner != guardian_name:
        frappe.throw(_("Acesso negado."), frappe.PermissionError)


def _academic_year_for_student(student_name):
    """Return the academic year of the student's current class group."""
    class_group = frappe.db.get_value("Student", student_name, "current_class_group")
    if not class_group:
        return None, None
    academic_year = frappe.db.get_value("Class Group", class_group, "academic_year")
    return class_group, academic_year


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_guardian_students():
    """Return all students linked to the current guardian plus guardian info."""
    guardian = _get_guardian()

    students = frappe.db.get_all(
        "Student",
        filters={"primary_guardian": guardian.name},
        fields=[
            "name", "full_name", "student_code",
            "current_school_class", "current_class_group",
            "current_status", "financial_status",
            "gender", "idade", "date_of_birth",
        ],
    )

    for s in students:
        if s.current_class_group:
            cg = frappe.db.get_value(
                "Class Group", s.current_class_group,
                ["shift", "academic_year"], as_dict=True,
            ) or {}
            s["shift"] = cg.get("shift") or ""
            s["academic_year"] = cg.get("academic_year") or ""
        else:
            s["shift"] = ""
            s["academic_year"] = ""

    return {
        "guardian": {
            "full_name": guardian.full_name or "",
            "email": guardian.email or "",
        },
        "students": students,
    }


# ---------------------------------------------------------------------------
# Student Hub — Resumo
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_student_summary(student):
    guardian = _get_guardian()
    _assert_owns_student(guardian.name, student)

    s = frappe.get_doc("Student", student)
    cg_data = {}
    if s.current_class_group:
        cg_data = frappe.db.get_value(
            "Class Group", s.current_class_group,
            ["shift", "academic_year", "class_teacher", "section_name"],
            as_dict=True,
        ) or {}

    return {
        "full_name": s.full_name or "",
        "student_code": s.student_code or "",
        "gender": s.gender or "",
        "date_of_birth": frappe.utils.formatdate(s.date_of_birth) if s.date_of_birth else "",
        "idade": s.idade or "",
        "place_of_birth": s.place_of_birth or "",
        "bi_number": s.bi_number or "",
        "admission_date": frappe.utils.formatdate(s.admission_date) if s.admission_date else "",
        "current_status": s.current_status or "",
        "financial_status": s.financial_status or "",
        "current_school_class": s.current_school_class or "",
        "current_class_group": s.current_class_group or "",
        "phone": s.phone or "",
        "address": s.address or "",
        "shift": cg_data.get("shift") or "",
        "academic_year": cg_data.get("academic_year") or "",
        "class_teacher": cg_data.get("class_teacher") or "",
    }


# ---------------------------------------------------------------------------
# Student Hub — Horário
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_student_timetable(student):
    guardian = _get_guardian()
    _assert_owns_student(guardian.name, student)

    class_group = frappe.db.get_value("Student", student, "current_class_group")
    if not class_group:
        return {"entries": [], "time_slots": []}

    timetable_name = frappe.db.get_value(
        "Timetable",
        {"class_group": class_group, "status": "Activo"},
        "name",
    )
    if not timetable_name:
        return {"entries": [], "time_slots": []}

    entries = frappe.db.get_all(
        "Timetable Entry",
        filters={"parent": timetable_name},
        fields=["day_of_week", "time_slot", "subject", "teacher", "is_double"],
    )

    shift = frappe.db.get_value("Class Group", class_group, "shift")
    ts_filters = {"shift": shift} if shift else {}
    time_slots = frappe.db.get_all(
        "Time Slot",
        filters=ts_filters,
        fields=["name", "label", "start_time", "end_time", "slot_type", "sort_order"],
        order_by="sort_order",
    )

    return {"entries": entries, "time_slots": time_slots}


# ---------------------------------------------------------------------------
# Student Hub — Notas
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_student_grades(student):
    guardian = _get_guardian()
    _assert_owns_student(guardian.name, student)

    class_group, academic_year = _academic_year_for_student(student)
    if not academic_year:
        return {"rows": [], "academic_year": None}

    rows = frappe.db.sql("""
        SELECT
            COALESCE(NULLIF(ger.subject, ''), ge.subject) AS subject,
            ger.score,
            ger.is_absent,
            ger.is_approved,
            ge.academic_term,
            ge.evaluation_type,
            ge.assessment_name,
            ge.assessment_date,
            ge.max_score
        FROM `tabGrade Entry Row` ger
        JOIN `tabGrade Entry` ge ON ge.name = ger.parent
        WHERE ger.student = %s
          AND ge.academic_year = %s
        ORDER BY ge.academic_term, ger.subject, ge.assessment_date
    """, (student, academic_year), as_dict=True)

    for r in rows:
        if r.assessment_date:
            r["assessment_date"] = frappe.utils.formatdate(r["assessment_date"])

    return {"rows": rows, "academic_year": academic_year}


# ---------------------------------------------------------------------------
# Student Hub — Boletim
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_student_boletim(student):
    guardian = _get_guardian()
    _assert_owns_student(guardian.name, student)

    class_group, academic_year = _academic_year_for_student(student)
    if not academic_year:
        return {"annual_assessment": None, "report_card": None, "report_card_rows": [], "academic_year": None}

    aa = frappe.db.sql("""
        SELECT
            aar.term_1_average, aar.term_2_average, aar.term_3_average,
            aar.final_grade, aar.result, aar.total_absences, aar.remarks
        FROM `tabAnnual Assessment Row` aar
        JOIN `tabAnnual Assessment` aa ON aa.name = aar.parent
        WHERE aar.student = %s AND aa.academic_year = %s
        LIMIT 1
    """, (student, academic_year), as_dict=True)

    rc = frappe.db.get_value(
        "Report Card",
        {"student": student, "academic_year": academic_year},
        ["name", "overall_average", "final_decision", "teacher_comment", "management_comment"],
        as_dict=True,
    )
    rc_rows = []
    if rc:
        rc_rows = frappe.db.get_all(
            "Report Card Row",
            filters={"parent": rc.name},
            fields=["subject", "final_grade", "result", "remarks"],
            order_by="subject",
        )

    return {
        "academic_year": academic_year,
        "annual_assessment": aa[0] if aa else None,
        "report_card": rc,
        "report_card_rows": rc_rows,
    }


# ---------------------------------------------------------------------------
# Student Hub — Presenças
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_student_attendance(student):
    guardian = _get_guardian()
    _assert_owns_student(guardian.name, student)

    class_group, academic_year = _academic_year_for_student(student)
    if not academic_year:
        return {"rows": [], "academic_year": None, "max_threshold": 0}

    rows = frappe.db.sql("""
        SELECT
            tar.justified_absences,
            tar.unjustified_absences,
            tar.total_absences,
            tar.at_risk,
            ta.academic_term
        FROM `tabTerm Attendance Row` tar
        JOIN `tabTerm Attendance` ta ON ta.name = tar.parent
        WHERE tar.student = %s AND ta.academic_year = %s
        ORDER BY ta.academic_term
    """, (student, academic_year), as_dict=True)

    max_threshold = int(frappe.db.get_single_value("School Settings", "max_absences_threshold") or 0)

    return {
        "rows": rows,
        "academic_year": academic_year,
        "max_threshold": max_threshold,
    }


# ---------------------------------------------------------------------------
# Student Hub — Financeiro
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_student_invoices(student):
    guardian = _get_guardian()
    _assert_owns_student(guardian.name, student)

    invoices = frappe.db.sql("""
        SELECT name, posting_date, due_date, grand_total, outstanding_amount, status
        FROM `tabSales Invoice`
        WHERE escola_student = %s AND docstatus != 2
        ORDER BY posting_date DESC
    """, student, as_dict=True)

    for inv in invoices:
        inv["posting_date"] = frappe.utils.formatdate(inv["posting_date"]) if inv["posting_date"] else ""
        inv["due_date"] = frappe.utils.formatdate(inv["due_date"]) if inv["due_date"] else ""
        inv["grand_total"] = float(inv["grand_total"] or 0)
        inv["outstanding_amount"] = float(inv["outstanding_amount"] or 0)

    total_outstanding = sum(i["outstanding_amount"] for i in invoices)
    financial_status = frappe.db.get_value("Student", student, "financial_status") or ""

    return {
        "invoices": invoices,
        "total_outstanding": total_outstanding,
        "financial_status": financial_status,
    }


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_guardian_profile():
    guardian = _get_guardian()
    return {
        "full_name": guardian.full_name or "",
        "phone": guardian.phone or "",
        "alternative_phone": guardian.alternative_phone or "",
        "email": guardian.email or "",
        "address": guardian.address or "",
    }


@frappe.whitelist()
def update_guardian_profile(phone, alternative_phone, email, address):
    guardian = _get_guardian()
    frappe.db.set_value("Guardian", guardian.name, {
        "phone": phone or "",
        "alternative_phone": alternative_phone or "",
        "email": email or "",
        "address": address or "",
    }, update_modified=True)
    return True


@frappe.whitelist()
def change_portal_password(current_pw, new_pw):
    guardian = _get_guardian()

    if len(new_pw) < 8:
        frappe.throw(_("A nova senha deve ter pelo menos 8 caracteres."))

    try:
        check_password(frappe.session.user, current_pw)
    except Exception:
        frappe.throw(_("A senha actual está incorrecta."))

    update_password(frappe.session.user, new_pw)

    # Clear the visible temp password now that a real password is set
    frappe.db.set_value("Guardian", guardian.name, "portal_password", "", update_modified=False)

    return True
