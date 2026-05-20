"""
escola/renewal_hold.py

Handles the automatic renewal hold process for returning students.

Flow:
  Daily scheduler (apply_renewal_hold):
    - Finds promoted students with no completed Renovacao once the
      academic year grace period has passed.
    - Sets student status → "Pendente de Renovação", SGA → Inactiva.

  After guardian pays (called from renovacao JS):
    - get_reactivation_options: returns available class groups.
    - reactivate_student: assigns class group, restores Activo.

Only affects returning students (promoted via Student Promotion).
New enrolments via Inscricao are excluded — they pay at registration.
"""

import frappe
from frappe import _
from frappe.utils import getdate, today


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------

def apply_renewal_hold():
    """
    Daily task: scan active SGAs for years that have started (past grace period)
    and put unpaid returning students on hold.
    """
    settings = frappe.get_single("School Settings")
    if not int(settings.get("renewal_auto_hold_enabled") or 0):
        return

    grace_days = int(settings.get("renewal_hold_grace_days") or 0)
    today_date = getdate(today())

    started_years = frappe.db.sql(
        """
        SELECT name
        FROM `tabAcademic Year`
        WHERE DATE_ADD(year_start_date, INTERVAL %s DAY) <= %s
        """,
        (grace_days, today_date),
        pluck="name",
    )

    if not started_years:
        return

    for academic_year in started_years:
        _hold_students_for_year(academic_year)

    frappe.db.commit()


def _hold_students_for_year(academic_year):
    """Deactivate SGAs and set status for all eligible students in an academic year."""
    rows = frappe.db.sql(
        """
        SELECT
            sga.name    AS sga_name,
            sga.student
        FROM `tabStudent Group Assignment` sga
        JOIN `tabStudent` s ON s.name = sga.student
        WHERE sga.academic_year = %s
          AND sga.status = 'Activa'
          AND s.current_status NOT IN (
              'Pendente de Renovação', 'Transferido', 'Desistente', 'Concluiu'
          )
          AND sga.student NOT IN (
              /* New enrolments — already paid at registration */
              SELECT student
              FROM `tabInscricao`
              WHERE academic_year = %s
                AND docstatus = 1
          )
          AND sga.student NOT IN (
              /* Students who already completed renovation */
              SELECT student
              FROM `tabRenovacao De Matricula`
              WHERE target_academic_year = %s
                AND docstatus = 1
          )
        """,
        (academic_year, academic_year, academic_year),
        as_dict=True,
    )

    for row in rows:
        try:
            frappe.db.set_value("Student Group Assignment", row.sga_name, "status", "Inactiva")
            frappe.db.set_value("Student", row.student, "current_status", "Pendente de Renovação")
        except Exception:
            frappe.log_error(
                title=_("Erro — Bloqueio de Renovação"),
                message=frappe.get_traceback(),
            )


# ---------------------------------------------------------------------------
# Reactivation helpers (called from renovacao_de_matricula.js)
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_reactivation_options(doc_name):
    """
    Check if a submitted Renovacao needs student reactivation.
    Returns None if student is not on hold.
    Returns available class groups if student is Pendente de Renovação.
    """
    doc = frappe.get_doc("Renovacao De Matricula", doc_name)

    student_status = frappe.db.get_value("Student", doc.student, "current_status")
    if student_status != "Pendente de Renovação":
        return None

    # Find the most recently deactivated SGA for the target year — that was the original seat
    original_sga = frappe.db.sql(
        """
        SELECT class_group, school_class
        FROM `tabStudent Group Assignment`
        WHERE student = %s
          AND academic_year = %s
          AND status = 'Inactiva'
        ORDER BY modified DESC
        LIMIT 1
        """,
        (doc.student, doc.target_academic_year),
        as_dict=True,
    )

    original_group = original_sga[0].class_group if original_sga else None
    school_class = (
        original_sga[0].school_class
        if original_sga
        else frappe.db.get_value("Student", doc.student, "current_school_class")
    )

    # All active class groups for the same school_class and target year
    cg_rows = frappe.get_all(
        "Class Group",
        filters={
            "school_class":   school_class,
            "academic_year":  doc.target_academic_year,
            "is_active":      1,
        },
        fields=["name", "section_name", "max_students"],
    )

    available = []
    for cg in cg_rows:
        max_s = int(cg.max_students or 0)
        count = frappe.db.count(
            "Student Group Assignment",
            {"class_group": cg.name, "status": "Activa"},
        )
        if max_s and count >= max_s:
            continue  # no vacancy
        available.append({
            "name":          cg.name,
            "section_name":  cg.section_name or "",
            "max_students":  max_s,
            "current_count": count,
            "is_original":   cg.name == original_group,
        })

    # Original group first, then alphabetical
    available.sort(key=lambda g: (0 if g["is_original"] else 1, g["name"]))

    student_name = frappe.db.get_value("Student", doc.student, "full_name")

    return {
        "student":              doc.student,
        "student_name":         student_name,
        "target_year":          doc.target_academic_year,
        "original_class_group": original_group,
        "available_groups":     available,
    }


@frappe.whitelist()
def reactivate_student(student, class_group, academic_year):
    """
    Assign a class group to a student coming off hold after paying renovation.
    Creates a fresh SGA and restores current_status = Activo.
    """
    current_status = frappe.db.get_value("Student", student, "current_status")
    if current_status != "Pendente de Renovação":
        frappe.throw(
            _("O aluno {0} não está em estado Pendente de Renovação (estado actual: {1}).").format(
                student, current_status
            )
        )

    # Vacancy check
    max_students = int(frappe.db.get_value("Class Group", class_group, "max_students") or 0)
    if max_students:
        count = frappe.db.count(
            "Student Group Assignment",
            {"class_group": class_group, "status": "Activa"},
        )
        if count >= max_students:
            frappe.throw(
                _("A turma <b>{0}</b> não tem vagas disponíveis ({1}/{2}).").format(
                    class_group, count, max_students
                )
            )

    school_class = frappe.db.get_value("Class Group", class_group, "school_class")

    sga = frappe.new_doc("Student Group Assignment")
    sga.student         = student
    sga.academic_year   = academic_year
    sga.school_class    = school_class
    sga.class_group     = class_group
    sga.assignment_date = today()
    sga.status          = "Activa"
    sga.notes           = _("Reactivado após pagamento de renovação de matrícula.")
    sga.insert(ignore_permissions=True)

    frappe.db.set_value("Student", student, {
        "current_status":      "Activo",
        "current_class_group": class_group,
        "current_school_class": school_class,
    })

    frappe.db.commit()
    return {"sga": sga.name, "class_group": class_group}
