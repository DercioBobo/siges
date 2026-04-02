"""
escola/public_api.py

Public (unauthenticated) API endpoints for the school public portal.
All methods use allow_guest=True — never expose personal student/guardian data.
"""
import frappe


@frappe.whitelist(allow_guest=True)
def get_turmas():
    """Return all active class groups for the current academic year."""
    academic_year = frappe.db.get_single_value("School Settings", "current_academic_year")
    if not academic_year:
        return {"turmas": [], "academic_year": None}

    turmas = frappe.db.get_all(
        "Class Group",
        filters={"academic_year": academic_year, "is_active": 1},
        fields=["name", "school_class", "shift", "class_teacher",
                "student_count", "max_students", "section_name"],
        order_by="school_class, section_name",
    )

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
def get_academic_calendar():
    """Return academic year and term dates."""
    academic_year = frappe.db.get_single_value("School Settings", "current_academic_year")
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
