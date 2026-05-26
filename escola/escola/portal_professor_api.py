"""
escola/portal_professor_api.py

Authenticated API endpoints for the Teacher Portal.
Trust chain: frappe.session.user → Teacher (user_id) → owns data
"""
import frappe
from frappe import _
from frappe.utils import getdate, today, nowdate
from frappe.utils.password import check_password, update_password


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def _get_teacher():
    user = frappe.session.user
    if not user or user == "Guest":
        frappe.throw(_("Sessão inválida."), frappe.AuthenticationError)

    teacher = frappe.db.get_value(
        "Teacher",
        {"user_id": user},
        ["name", "full_name", "teacher_code", "is_active", "email", "phone"],
        as_dict=True,
    )
    if not teacher:
        frappe.throw(_("Nenhum professor associado a este utilizador."), frappe.PermissionError)
    if not teacher.is_active:
        frappe.throw(_("A sua conta de professor está desactivada."), frappe.PermissionError)
    return teacher


def _get_teacher_turmas(teacher_name):
    """Return all active turmas the teacher is involved with (director + subject teacher)."""
    academic_year = frappe.db.get_single_value("School Settings", "current_academic_year")
    year_sql = "AND cg.academic_year = %s" if academic_year else ""

    # 1. Turmas where teacher is class director
    director_set = set()
    cg_filters = {"class_teacher": teacher_name, "is_active": 1}
    if academic_year:
        cg_filters["academic_year"] = academic_year
    for cg in frappe.db.get_all("Class Group", filters=cg_filters, fields=["name"]):
        director_set.add(cg.name)

    # 2. Turmas from active timetable entries
    params = (teacher_name, academic_year) if academic_year else (teacher_name,)
    timetable_cgs = frappe.db.sql(f"""
        SELECT DISTINCT t.class_group
        FROM `tabTimetable Entry` te
        JOIN `tabTimetable` t ON t.name = te.parent
        JOIN `tabClass Group` cg ON cg.name = t.class_group
        WHERE te.teacher = %s AND t.status = 'Activo' AND cg.is_active = 1
        {year_sql}
    """, params, as_dict=True)

    # 3. Turmas from School Class Subject assignments
    sc_year_sql = "AND cg.academic_year = %s" if academic_year else ""
    sc_params = (teacher_name, academic_year) if academic_year else (teacher_name,)
    scs_cgs = frappe.db.sql(f"""
        SELECT DISTINCT cg.name
        FROM `tabSchool Class Subject` scs
        JOIN `tabClass Group` cg ON cg.school_class = scs.parent
        WHERE scs.teacher = %s AND cg.is_active = 1
        {sc_year_sql}
    """, sc_params, as_dict=True)

    all_names = director_set | {r.class_group for r in timetable_cgs} | {r.name for r in scs_cgs}
    if not all_names:
        return []

    turmas = frappe.db.get_all(
        "Class Group",
        filters={"name": ("in", list(all_names))},
        fields=["name", "school_class", "shift", "section_name", "academic_year", "student_count", "max_students"],
        order_by="school_class, section_name",
    )
    for t in turmas:
        t["is_director"] = t.name in director_set
    return turmas


def _assert_teacher_owns_turma(teacher_name, turma):
    """Raise PermissionError if teacher has no connection to the given turma."""
    owned = {t["name"] for t in _get_teacher_turmas(teacher_name)}
    if turma not in owned:
        frappe.throw(_("Acesso negado a esta turma."), frappe.PermissionError)


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_dashboard():
    teacher = _get_teacher()
    turmas = _get_teacher_turmas(teacher.name)
    academic_year = frappe.db.get_single_value("School Settings", "current_academic_year")

    # Today's lessons from timetable
    DAY_MAP = {
        "Monday":    "Segunda-Feira",
        "Tuesday":   "Terça-Feira",
        "Wednesday": "Quarta-Feira",
        "Thursday":  "Quinta-Feira",
        "Friday":    "Sexta-Feira",
        "Saturday":  "Sábado",
        "Sunday":    "Domingo",
    }
    import datetime
    today_pt = DAY_MAP.get(datetime.datetime.now().strftime("%A"), "")

    today_lessons = []
    if today_pt:
        today_lessons = frappe.db.sql("""
            SELECT te.subject, te.time_slot,
                   t.class_group, cg.school_class, cg.section_name, cg.shift,
                   ts.start_time, ts.label
            FROM `tabTimetable Entry` te
            JOIN `tabTimetable` t ON t.name = te.parent
            JOIN `tabClass Group` cg ON cg.name = t.class_group
            LEFT JOIN `tabTime Slot` ts ON ts.name = te.time_slot
            WHERE te.teacher = %s AND te.day_of_week = %s AND t.status = 'Activo'
            ORDER BY ts.sort_order
        """, (teacher.name, today_pt), as_dict=True)

    # Stats
    total_students = sum(t.get("student_count") or 0 for t in turmas)

    at_risk = 0
    max_threshold = int(frappe.db.get_single_value("School Settings", "max_absences_threshold") or 0)
    if max_threshold and turmas:
        at_risk = frappe.db.sql("""
            SELECT COUNT(*) FROM `tabTerm Attendance Row` tar
            JOIN `tabTerm Attendance` ta ON ta.name = tar.parent
            WHERE ta.class_group IN %s AND tar.at_risk = 1
        """, [tuple(t["name"] for t in turmas)])[0][0] or 0

    # Recent grade entries
    recent_entries = []
    if turmas:
        recent_entries = frappe.db.get_all(
            "Grade Entry",
            filters={
                "class_group": ("in", [t["name"] for t in turmas]),
                "docstatus": ("!=", 2),
            },
            fields=["name", "class_group", "academic_term", "subject"],
            order_by="modified desc",
            limit=5,
        )

    return {
        "teacher": {
            "name": teacher.name,
            "full_name": teacher.full_name,
            "teacher_code": teacher.teacher_code,
            "email": teacher.email or "",
            "phone": teacher.phone or "",
        },
        "turmas": turmas,
        "today_lessons": today_lessons,
        "stats": {
            "total_turmas": len(turmas),
            "total_students": total_students,
            "at_risk": at_risk,
        },
        "recent_entries": recent_entries,
        "academic_year": academic_year or "",
    }


# ---------------------------------------------------------------------------
# Timetable
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_timetable():
    teacher = _get_teacher()

    entries = frappe.db.sql("""
        SELECT te.day_of_week, te.time_slot, te.subject,
               t.class_group, cg.school_class, cg.section_name, cg.shift,
               ts.start_time, ts.end_time, ts.label, ts.sort_order, ts.slot_type
        FROM `tabTimetable Entry` te
        JOIN `tabTimetable` t ON t.name = te.parent
        JOIN `tabClass Group` cg ON cg.name = t.class_group
        LEFT JOIN `tabTime Slot` ts ON ts.name = te.time_slot
        WHERE te.teacher = %s AND t.status = 'Activo'
        ORDER BY ts.sort_order, te.day_of_week
    """, teacher.name, as_dict=True)

    # All relevant time slots
    time_slots = frappe.db.sql("""
        SELECT DISTINCT ts.name, ts.label, ts.start_time, ts.end_time, ts.slot_type, ts.sort_order
        FROM `tabTime Slot` ts
        WHERE ts.name IN (
            SELECT te.time_slot FROM `tabTimetable Entry` te
            JOIN `tabTimetable` t ON t.name = te.parent
            WHERE te.teacher = %s AND t.status = 'Activo'
        )
        ORDER BY ts.sort_order
    """, teacher.name, as_dict=True)

    return {"entries": entries, "time_slots": time_slots}


# ---------------------------------------------------------------------------
# Turma detail
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_turma_students(turma):
    teacher = _get_teacher()
    _assert_teacher_owns_turma(teacher.name, turma)

    students = frappe.db.sql("""
        SELECT cgs.student, cgs.student_name, s.student_code, s.financial_status
        FROM `tabClass Group Student` cgs
        LEFT JOIN `tabStudent` s ON s.name = cgs.student
        WHERE cgs.parent = %s AND cgs.parentfield = 'students'
        ORDER BY cgs.student_name
    """, turma, as_dict=True)

    return {"students": students, "total": len(students)}


# ---------------------------------------------------------------------------
# Grade entries
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_grade_entries(turma, term):
    teacher = _get_teacher()
    _assert_teacher_owns_turma(teacher.name, turma)

    # Subjects this teacher teaches in this turma (from active timetable)
    subj_rows = frappe.db.sql("""
        SELECT DISTINCT te.subject
        FROM `tabTimetable Entry` te
        JOIN `tabTimetable` t ON t.name = te.parent
        WHERE te.teacher = %s AND t.class_group = %s AND t.status = 'Activo'
          AND te.subject IS NOT NULL AND te.subject != ''
        ORDER BY te.subject
    """, (teacher.name, turma), as_dict=True)
    subj_names = [r.subject for r in subj_rows]

    # Fall back to School Class subjects when teacher has no timetable entries (e.g. class director)
    if not subj_names:
        school_class = frappe.db.get_value("Class Group", turma, "school_class")
        if school_class:
            lines = frappe.get_all(
                "School Class Subject",
                filters={"parent": school_class},
                fields=["subject"],
                order_by="idx asc",
            )
            subj_names = [l.subject for l in lines if l.subject]

    if not subj_names:
        return {"entries": []}

    # Batch-fetch all Grade Entries for this turma/term
    existing_ges = {
        ge.subject: ge
        for ge in frappe.get_all(
            "Grade Entry",
            filters={"class_group": turma, "academic_term": term, "docstatus": ("!=", 2)},
            fields=["name", "subject"],
        )
    }

    student_count = frappe.db.count(
        "Class Group Student",
        {"parent": turma, "parentfield": "students"},
    )

    entries = []
    for sn in subj_names:
        ge = existing_ges.get(sn)
        counts = {"complete": 0, "in_progress": 0, "absent": 0, "total": student_count}
        status = "Vazio"

        if ge:
            for r in frappe.get_all(
                "Grade Entry Row",
                filters={"parent": ge.name},
                fields=["is_absent", "mt"],
            ):
                if r.is_absent:
                    counts["absent"] += 1
                    counts["complete"] += 1
                elif r.mt is not None:
                    counts["complete"] += 1
                else:
                    counts["in_progress"] += 1

            if counts["complete"] + counts["in_progress"] == 0:
                status = "Vazio"
            elif counts["complete"] >= student_count:
                status = "Completo"
            else:
                status = "Em Curso"

        entries.append({
            "subject": sn,
            "entry_name": ge.name if ge else None,
            "status": status,
            "counts": counts,
        })

    return {"entries": entries}


@frappe.whitelist()
def get_grade_entry_rows(turma, term, subject):
    teacher = _get_teacher()
    _assert_teacher_owns_turma(teacher.name, turma)

    ge_name = frappe.db.get_value(
        "Grade Entry",
        {"class_group": turma, "academic_term": term, "subject": subject, "docstatus": ("!=", 2)},
        "name",
    )

    students = frappe.db.sql("""
        SELECT cgs.student, cgs.student_name, s.student_code
        FROM `tabClass Group Student` cgs
        LEFT JOIN `tabStudent` s ON s.name = cgs.student
        WHERE cgs.parent = %s AND cgs.parentfield = 'students'
        ORDER BY cgs.student_name
    """, turma, as_dict=True)

    existing = {}
    if ge_name:
        for r in frappe.get_all(
            "Grade Entry Row",
            filters={"parent": ge_name},
            fields=["student", "acsp_1", "acsp_2", "acsp_3",
                    "acse_1", "acse_2", "acse_3", "acp",
                    "macsp", "macs", "mt", "is_absent"],
        ):
            existing[r.student] = r

    rows = []
    for s in students:
        ex = existing.get(s.student, {})
        rows.append({
            "student":      s.student,
            "student_name": s.student_name or s.student,
            "student_code": s.student_code or "",
            "acsp_1":  ex.get("acsp_1"),
            "acsp_2":  ex.get("acsp_2"),
            "acsp_3":  ex.get("acsp_3"),
            "acse_1":  ex.get("acse_1"),
            "acse_2":  ex.get("acse_2"),
            "acse_3":  ex.get("acse_3"),
            "acp":     ex.get("acp"),
            "macsp":   ex.get("macsp"),
            "macs":    ex.get("macs"),
            "mt":      ex.get("mt"),
            "is_absent": int(ex.get("is_absent") or 0),
        })

    return {"entry_name": ge_name, "subject": subject, "rows": rows}


@frappe.whitelist()
def save_grade_entry(turma, term, subject, rows, notes=None):
    teacher = _get_teacher()
    _assert_teacher_owns_turma(teacher.name, turma)

    import json
    if isinstance(rows, str):
        rows = json.loads(rows)

    student_names = {
        s.name: s.full_name
        for s in frappe.get_all(
            "Student",
            filters={"name": ("in", [r["student"] for r in rows])},
            fields=["name", "full_name"],
        )
    }

    def _apply(row, data):
        for f in ["acsp_1", "acsp_2", "acsp_3", "acse_1", "acse_2", "acse_3", "acp"]:
            v = data.get(f)
            row.set(f, float(v) if v is not None and v != "" else None)
        row.is_absent = int(data.get("is_absent") or 0)

    ge_name = frappe.db.get_value(
        "Grade Entry",
        {"class_group": turma, "academic_term": term, "subject": subject, "docstatus": ("!=", 2)},
        "name",
    )

    if ge_name:
        doc = frappe.get_doc("Grade Entry", ge_name)
        by_student = {r.student: r for r in doc.grade_rows}
        for r in rows:
            if r["student"] in by_student:
                _apply(by_student[r["student"]], r)
            else:
                new_row = doc.append("grade_rows", {
                    "student": r["student"],
                    "student_name": student_names.get(r["student"], ""),
                })
                _apply(new_row, r)
    else:
        cg_info = frappe.db.get_value(
            "Class Group", turma, ["academic_year", "school_class"], as_dict=True
        ) or {}
        doc = frappe.new_doc("Grade Entry")
        doc.class_group   = turma
        doc.academic_term = term
        doc.subject       = subject
        doc.academic_year = cg_info.get("academic_year") or ""
        doc.school_class  = cg_info.get("school_class") or ""
        doc.teacher       = teacher.name
        for r in rows:
            new_row = doc.append("grade_rows", {
                "student": r["student"],
                "student_name": student_names.get(r["student"], ""),
            })
            _apply(new_row, r)

    doc.save(ignore_permissions=True)
    frappe.db.commit()

    saved_rows = frappe.get_all(
        "Grade Entry Row",
        filters={"parent": doc.name},
        fields=["student", "acsp_1", "acsp_2", "acsp_3",
                "acse_1", "acse_2", "acse_3", "acp",
                "macsp", "macs", "mt", "is_absent"],
        order_by="idx asc",
    )

    current_set = {r["student"] for r in rows}
    status_rows = [sr for sr in saved_rows if sr.student in current_set]

    from escola.escola.page.mapa_aproveitamento.mapa_aproveitamento import _subject_status
    return {
        "name": doc.name,
        "created": not ge_name,
        "status": _subject_status(status_rows),
        "rows": saved_rows,
    }


# ---------------------------------------------------------------------------
# Attendance
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_attendance(turma, term):
    teacher = _get_teacher()
    _assert_teacher_owns_turma(teacher.name, turma)

    att_name = frappe.db.get_value(
        "Term Attendance",
        {"class_group": turma, "academic_term": term},
        "name",
    )

    if not att_name:
        # Return blank rows for all students in turma
        students = frappe.db.sql("""
            SELECT cgs.student, cgs.student_name
            FROM `tabClass Group Student` cgs
            WHERE cgs.parent = %s AND cgs.parentfield = 'students'
            ORDER BY cgs.student_name
        """, turma, as_dict=True)
        return {
            "exists": False,
            "rows": [{"student": s.student, "student_name": s.student_name,
                      "justified_absences": 0, "unjustified_absences": 0,
                      "total_absences": 0, "at_risk": 0} for s in students],
        }

    rows = frappe.db.get_all(
        "Term Attendance Row",
        filters={"parent": att_name},
        fields=["student", "justified_absences", "unjustified_absences", "total_absences", "at_risk"],
        order_by="student",
    )
    student_names = {r.student: frappe.db.get_value("Student", r.student, "full_name") or r.student for r in rows}
    for r in rows:
        r["student_name"] = student_names.get(r.student, r.student)

    return {"exists": True, "att_name": att_name, "rows": rows}


@frappe.whitelist()
def save_attendance(turma, term, rows):
    teacher = _get_teacher()
    _assert_teacher_owns_turma(teacher.name, turma)

    import json
    if isinstance(rows, str):
        rows = json.loads(rows)

    max_threshold = int(frappe.db.get_single_value("School Settings", "max_absences_threshold") or 0)
    cg = frappe.db.get_value("Class Group", turma, ["school_class", "academic_year"], as_dict=True) or {}

    existing = frappe.db.get_value(
        "Term Attendance",
        {"class_group": turma, "academic_term": term},
        "name",
    )

    if existing:
        att = frappe.get_doc("Term Attendance", existing)
    else:
        att = frappe.new_doc("Term Attendance")
        att.class_group   = turma
        att.academic_term = term
        att.school_class  = cg.get("school_class") or ""
        att.academic_year = cg.get("academic_year") or ""

    att.set("attendance_rows", [])
    at_risk_count = 0
    for r in rows:
        justified   = int(r.get("justified_absences")   or 0)
        unjustified = int(r.get("unjustified_absences") or 0)
        total       = justified + unjustified
        at_risk     = 1 if (max_threshold and total >= max_threshold) else 0
        if at_risk:
            at_risk_count += 1
        att.append("attendance_rows", {
            "student":               r.get("student"),
            "justified_absences":    justified,
            "unjustified_absences":  unjustified,
            "total_absences":        total,
            "at_risk":               at_risk,
        })

    att.total_students   = len(rows)
    att.students_at_risk = at_risk_count

    if existing:
        att.save(ignore_permissions=True)
    else:
        att.insert(ignore_permissions=True)

    frappe.db.commit()
    return {"name": att.name, "created": not existing}


# ---------------------------------------------------------------------------
# Academic terms
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_terms():
    academic_year = frappe.db.get_single_value("School Settings", "current_academic_year")
    if not academic_year:
        return {"terms": [], "academic_year": None}

    terms = frappe.db.get_all(
        "Academic Term",
        filters={"academic_year": academic_year},
        fields=["name", "term_name", "start_date", "end_date"],
        order_by="start_date",
    )
    today_d = getdate(today())
    current = None
    for t in terms:
        if t.start_date and t.end_date:
            if getdate(t.start_date) <= today_d <= getdate(t.end_date):
                current = t.name
                break
    return {"terms": terms, "academic_year": academic_year, "current_term": current}


# ---------------------------------------------------------------------------
# Subjects for a turma (teacher-filtered)
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_teacher_subjects(turma):
    """Return subjects the teacher teaches in the given turma (from active timetable)."""
    teacher = _get_teacher()
    _assert_teacher_owns_turma(teacher.name, turma)

    # Subjects this teacher teaches in this specific turma
    rows = frappe.db.sql("""
        SELECT DISTINCT te.subject
        FROM `tabTimetable Entry` te
        JOIN `tabTimetable` t ON t.name = te.parent
        WHERE te.teacher = %s AND t.class_group = %s AND t.status = 'Activo'
          AND te.subject IS NOT NULL AND te.subject != ''
        ORDER BY te.subject
    """, (teacher.name, turma), as_dict=True)

    subjects = [r.subject for r in rows]

    # If class director with no specific subject assignments, fall back to all subjects in turma timetable
    if not subjects:
        cg_teacher = frappe.db.get_value("Class Group", turma, "class_teacher")
        if cg_teacher == teacher.name:
            all_rows = frappe.db.sql("""
                SELECT DISTINCT te.subject
                FROM `tabTimetable Entry` te
                JOIN `tabTimetable` t ON t.name = te.parent
                WHERE t.class_group = %s AND t.status = 'Activo'
                  AND te.subject IS NOT NULL AND te.subject != ''
                ORDER BY te.subject
            """, turma, as_dict=True)
            subjects = [r.subject for r in all_rows]

    return {"subjects": subjects}


# ---------------------------------------------------------------------------
# Profile / password
# ---------------------------------------------------------------------------

@frappe.whitelist()
def change_portal_password(current_pw, new_pw):
    _get_teacher()
    if len(new_pw) < 8:
        frappe.throw(_("A nova senha deve ter pelo menos 8 caracteres."))
    try:
        check_password(frappe.session.user, current_pw)
    except Exception:
        frappe.throw(_("A senha actual está incorrecta."))
    update_password(frappe.session.user, new_pw)
    return True
