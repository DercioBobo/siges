"""
Switch Student IDs from the full name to the student code (ALU-00001).

1. Make sure every Student has a unique student_code (fills blanks, re-codes
   duplicates — the oldest record keeps the original code).
2. Move the "ALU-" naming series counter up to the highest existing code, so
   new students continue the sequence.
3. Rename every Student whose ID is not its code. frappe.rename_doc updates
   every Link field pointing at Student (invoices, customers, turmas, grades,
   attendance, ...), so no history is lost.
4. Fill the new student_name columns on doctypes that link to Student.

Idempotent: renames are committed in batches and a re-run only picks up the
students that still need it.
"""

import frappe

SERIES_KEY = "ALU-"

# Doctypes that received a `student_name` field (fetch_from student.full_name)
STUDENT_NAME_DOCTYPES = (
    "Academic Closure Row",
    "Annual Assessment Row",
    "Student Attendance Entry",
    "Student Promotion Row",
    "Term Attendance Row",
    "Renovacao De Matricula",
    "Report Card",
    "Student Transfer",
    "Troca De Turma",
    "Student Group Assignment",
)


def execute():
    frappe.flags.escola_student_id_migration = True
    try:
        _ensure_unique_codes()
        _sync_series()
        _rename_students()
        _backfill_student_names()
    finally:
        frappe.flags.escola_student_id_migration = False
    frappe.clear_cache(doctype="Student")


def _code_seq(code):
    if code and code.startswith(SERIES_KEY):
        try:
            return int(code[len(SERIES_KEY):])
        except ValueError:
            pass
    return 0


def _ensure_unique_codes():
    students = frappe.db.sql(
        "SELECT name, student_code FROM `tabStudent` ORDER BY creation ASC, name ASC",
        as_dict=True,
    )
    max_seq = max((_code_seq(s.student_code) for s in students), default=0)

    seen = set()
    for s in students:
        code = (s.student_code or "").strip()
        if code and code not in seen:
            seen.add(code)
            continue
        max_seq += 1
        new_code = "{0}{1:05d}".format(SERIES_KEY, max_seq)
        frappe.db.set_value("Student", s.name, "student_code", new_code, update_modified=False)
        seen.add(new_code)
    frappe.db.commit()


def _sync_series():
    max_seq = max(
        (_code_seq(c) for c in frappe.db.sql_list("SELECT student_code FROM `tabStudent`")),
        default=0,
    )
    current = frappe.db.sql("SELECT current FROM `tabSeries` WHERE name = %s", SERIES_KEY)
    if not current:
        frappe.db.sql("INSERT INTO `tabSeries` (name, current) VALUES (%s, %s)", (SERIES_KEY, max_seq))
    elif (current[0][0] or 0) < max_seq:
        frappe.db.sql("UPDATE `tabSeries` SET current = %s WHERE name = %s", (max_seq, SERIES_KEY))
    frappe.db.commit()


def _rename_students():
    rows = frappe.db.sql(
        "SELECT name, student_code FROM `tabStudent` "
        "WHERE name != student_code ORDER BY creation ASC",
        as_dict=True,
    )
    for i, r in enumerate(rows, start=1):
        frappe.rename_doc(
            "Student",
            r.name,
            r.student_code,
            force=True,
            ignore_permissions=True,
            show_alert=False,
            rebuild_search=False,
        )
        if i % 50 == 0:
            frappe.db.commit()
    frappe.db.commit()


def _backfill_student_names():
    for dt in STUDENT_NAME_DOCTYPES:
        if not frappe.db.has_column(dt, "student_name"):
            continue
        frappe.db.sql(
            f"""
            UPDATE `tab{dt}` t
            JOIN `tabStudent` s ON s.name = t.student
            SET t.student_name = s.full_name
            """
        )
    frappe.db.commit()
