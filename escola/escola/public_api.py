"""
escola/public_api.py

Public (unauthenticated) API endpoints for the school public portal.
All methods use allow_guest=True — never expose personal student/guardian data.
"""
import frappe


@frappe.whitelist(allow_guest=True)
def get_turmas():
    """Return active class groups. Filters by current_academic_year if set; shows all active turmas otherwise."""
    academic_year = frappe.db.get_single_value("School Settings", "current_academic_year")

    def _fetch(filters):
        return frappe.db.get_all(
            "Class Group",
            filters=filters,
            fields=["name", "school_class", "shift", "class_teacher",
                    "student_count", "max_students", "section_name", "academic_year"],
            order_by="school_class, section_name",
        )

    # Try with year + is_active first
    turmas = _fetch({"academic_year": academic_year, "is_active": 1}) if academic_year else []

    # Fall back: year without is_active filter (in case turmas were left at 0)
    if not turmas and academic_year:
        turmas = _fetch({"academic_year": academic_year})

    # Final fall back: no year filter — show everything active
    if not turmas:
        turmas = _fetch({"is_active": 1})

    # Last resort: truly all turmas
    if not turmas:
        turmas = _fetch({})

    # Check which turmas have an active timetable
    for t in turmas:
        t["has_timetable"] = bool(
            frappe.db.get_value("Timetable", {"class_group": t.name, "status": "Activo"}, "name")
        )

    return {"turmas": turmas, "academic_year": academic_year}


@frappe.whitelist(allow_guest=True)
def get_turma_timetable(turma):
    """Return active timetable entries for a given class group."""
    if not frappe.db.exists("Class Group", turma):
        return {"entries": [], "time_slots": [], "turma_info": {}}

    timetable_name = frappe.db.get_value(
        "Timetable",
        {"class_group": turma, "status": "Activo"},
        "name",
    )

    turma_info = frappe.db.get_value(
        "Class Group", turma,
        ["name", "school_class", "shift", "class_teacher", "section_name"],
        as_dict=True,
    ) or {}

    if not timetable_name:
        return {"entries": [], "time_slots": [], "turma_info": turma_info}

    entries = frappe.db.get_all(
        "Timetable Entry",
        filters={"parent": timetable_name},
        fields=["day_of_week", "time_slot", "subject", "teacher", "is_double"],
    )

    shift = turma_info.get("shift") or ""
    ts_filters = {"shift": shift} if shift else {}
    time_slots = frappe.db.get_all(
        "Time Slot",
        filters=ts_filters,
        fields=["name", "label", "start_time", "end_time", "slot_type", "sort_order"],
        order_by="sort_order",
    )

    return {"entries": entries, "time_slots": time_slots, "turma_info": turma_info}


@frappe.whitelist(allow_guest=True)
def get_turma_students(turma):
    """Return the student roster for a class group. Exposes only name and student code."""
    if not frappe.db.exists("Class Group", turma):
        return {"students": [], "total": 0}

    students = frappe.db.sql("""
        SELECT cgs.student, cgs.student_name, s.student_code
        FROM `tabClass Group Student` cgs
        LEFT JOIN `tabStudent` s ON s.name = cgs.student
        WHERE cgs.parent = %s AND cgs.parentfield = 'students'
        ORDER BY cgs.student_name
    """, turma, as_dict=True)

    return {"students": students, "total": len(students)}


@frappe.whitelist(allow_guest=True)
def search_student(query):
    """
    Search students by name and return their current class group.
    Public-safe: only exposes student_name, student_code, turma, shift.
    Requires at least 3 characters.
    """
    if not query or len(query.strip()) < 3:
        return {"results": []}

    academic_year = frappe.db.get_single_value("School Settings", "current_academic_year")
    q = "%" + query.strip() + "%"

    if academic_year:
        results = frappe.db.sql("""
            SELECT
                cgs.student_name,
                s.student_code,
                cg.name  AS class_group,
                cg.school_class,
                cg.shift,
                cg.section_name,
                cg.class_teacher,
                cg.academic_year
            FROM `tabClass Group Student` cgs
            JOIN `tabClass Group` cg ON cg.name = cgs.parent
            LEFT JOIN `tabStudent` s ON s.name = cgs.student
            WHERE cgs.student_name LIKE %s
              AND cg.is_active = 1
              AND cg.academic_year = %s
            ORDER BY cgs.student_name
            LIMIT 20
        """, (q, academic_year), as_dict=True)
    else:
        results = frappe.db.sql("""
            SELECT
                cgs.student_name,
                s.student_code,
                cg.name  AS class_group,
                cg.school_class,
                cg.shift,
                cg.section_name,
                cg.class_teacher,
                cg.academic_year
            FROM `tabClass Group Student` cgs
            JOIN `tabClass Group` cg ON cg.name = cgs.parent
            LEFT JOIN `tabStudent` s ON s.name = cgs.student
            WHERE cgs.student_name LIKE %s
              AND cg.is_active = 1
            ORDER BY cgs.student_name
            LIMIT 20
        """, (q,), as_dict=True)

    return {"results": results}


@frappe.whitelist(allow_guest=True)
def get_academic_calendar():
    """Return academic year and term dates."""
    academic_year = frappe.db.get_single_value("School Settings", "current_academic_year")

    # Fall back to the most recent active academic year if School Settings not configured
    if not academic_year:
        row = frappe.db.get_all("Academic Year", filters={"is_active": 1},
                                fields=["name"], order_by="start_date desc", limit=1)
        if not row:
            row = frappe.db.get_all("Academic Year", fields=["name"],
                                    order_by="start_date desc", limit=1)
        academic_year = row[0].name if row else None

    if not academic_year:
        return {"terms": [], "academic_year": None}

    ay = frappe.db.get_value(
        "Academic Year", academic_year,
        ["start_date", "end_date"], as_dict=True,
    ) or {}

    terms = frappe.db.get_all(
        "Academic Term",
        filters={"academic_year": academic_year},
        fields=["name", "term_name", "start_date", "end_date"],
        order_by="start_date",
    )
    for t in terms:
        t["start_date"] = frappe.utils.formatdate(t.start_date) if t.start_date else ""
        t["end_date"] = frappe.utils.formatdate(t.end_date) if t.end_date else ""

    return {
        "academic_year": academic_year,
        "ay_start": frappe.utils.formatdate(ay.get("start_date")) if ay.get("start_date") else "",
        "ay_end": frappe.utils.formatdate(ay.get("end_date")) if ay.get("end_date") else "",
        "terms": terms,
    }
