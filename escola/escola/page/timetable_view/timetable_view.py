import frappe
from frappe import _
from collections import Counter


@frappe.whitelist()
def get_filter_options():
    """Return active academic terms and class groups for the filter bar."""
    terms = frappe.get_all(
        "Academic Term",
        filters={"is_active": 1},
        fields=["name", "term_name", "academic_year"],
        order_by="start_date desc",
    )
    class_groups = frappe.get_all(
        "Class Group",
        filters={"is_active": 1},
        fields=["name", "group_name", "shift", "school_class"],
        order_by="group_name asc",
    )
    return {"terms": terms, "class_groups": class_groups}


@frappe.whitelist()
def get_timetable_data(class_group, academic_term):
    """
    Return everything the JS renderer needs to draw the timetable grid.
    - time_slots: ordered list filtered by the turma's shift
    - grid: {day: {slot_name: cell_data}}
    - subjects_summary: weekly slot counts per subject
    """
    cg_info = frappe.db.get_value(
        "Class Group", class_group,
        ["group_name", "shift", "class_teacher", "school_class"],
        as_dict=True,
    )
    if cg_info and cg_info.class_teacher:
        cg_info["teacher_name"] = frappe.db.get_value("Teacher", cg_info.class_teacher, "full_name") or ""

    timetable = frappe.db.get_value(
        "Timetable",
        {"class_group": class_group, "academic_term": academic_term, "status": "Activo"},
        ["name", "status"],
        as_dict=True,
    )

    days = ["Segunda-Feira", "Terça-Feira", "Quarta-Feira", "Quinta-Feira", "Sexta-Feira"]

    if not timetable:
        return {
            "found":            False,
            "class_group_info": cg_info,
            "time_slots":       [],
            "days":             days,
            "grid":             {},
            "subjects_summary": [],
        }

    # Time slots filtered by shift of this class group
    ts_filters = {"is_active": 1}
    if cg_info and cg_info.shift:
        ts_filters["shift"] = cg_info.shift

    time_slots = frappe.get_all(
        "Time Slot",
        filters=ts_filters,
        fields=["name", "label", "slot_type"],
        order_by="label asc",
    )

    # All child entries for this timetable
    entries = frappe.get_all(
        "Timetable Entry",
        filters={"parent": timetable.name},
        fields=["day_of_week", "time_slot", "subject", "teacher", "is_double", "notes"],
    )

    # Resolve subject info (name, code, color)
    subject_names = list({e.subject for e in entries if e.subject})
    subject_map = {}
    if subject_names:
        for s in frappe.get_all(
            "Subject",
            filters={"name": ("in", subject_names)},
            fields=["name", "subject_name", "subject_code", "color"],
        ):
            subject_map[s.name] = s

    # Resolve teacher full names
    teacher_ids = list({e.teacher for e in entries if e.teacher})
    teacher_map = {}
    if teacher_ids:
        for t in frappe.get_all(
            "Teacher",
            filters={"name": ("in", teacher_ids)},
            fields=["name", "full_name"],
        ):
            teacher_map[t.name] = t.full_name

    # Build grid: {day: {time_slot_name: cell_data}}
    grid = {day: {} for day in days}
    for e in entries:
        sub = subject_map.get(e.subject) if e.subject else None
        grid[e.day_of_week][e.time_slot] = {
            "subject":      sub.subject_name if sub else "",
            "subject_code": sub.subject_code if sub else "",
            "color":        (sub.color or "") if sub else "",
            "teacher":      teacher_map.get(e.teacher, ""),
            "is_double":    int(e.is_double or 0),
            "notes":        e.notes or "",
        }

    # Weekly slot count per subject (for legend)
    counts = Counter(e.subject for e in entries if e.subject)
    subjects_summary = []
    for subj, count in sorted(counts.items(), key=lambda x: -x[1]):
        sub = subject_map.get(subj)
        if sub:
            subjects_summary.append({
                "subject":      sub.subject_name,
                "subject_code": sub.subject_code,
                "color":        sub.color or "",
                "slots":        count,
            })

    return {
        "found":            True,
        "timetable_name":   timetable.name,
        "class_group_info": cg_info,
        "time_slots":       time_slots,
        "days":             days,
        "grid":             grid,
        "subjects_summary": subjects_summary,
    }
