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
5. Drop the UNIQUE index Frappe put on full_name while it was the autoname
   field, so two students may share a name.

Idempotent: renames are committed in batches and a re-run only picks up the
students that still need it.

Health check (run before and after migrating, results should match):
    bench --site <site> execute escola.patches.v1_0.student_id_from_code.verify
"""

import frappe
from frappe.model.rename_doc import get_link_fields, rename_doc

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
        _drop_full_name_unique_index()
    finally:
        frappe.flags.escola_student_id_migration = False
    frappe.clear_cache(doctype="Student")
    # rename_doc was told not to rebuild per student — do it once here.
    # Only affects the global search bar, so never fail the migration over it.
    try:
        frappe.enqueue("frappe.utils.global_search.rebuild_for_doctype", doctype="Student")
    except Exception:
        frappe.log_error(title="Escola — reconstrução da pesquisa global de Alunos falhou")


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
        # frappe.model.rename_doc.rename_doc, not the frappe.rename_doc
        # wrapper — only the former accepts ignore_permissions
        rename_doc(
            doctype="Student",
            old=r.name,
            new=r.student_code,
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


def _drop_full_name_unique_index():
    # Schema sync normally drops it already; this is the safety net.
    unique_index = frappe.db.get_column_index("tabStudent", "full_name", unique=True)
    if unique_index:
        frappe.db.sql_ddl(f"ALTER TABLE `tabStudent` DROP INDEX `{unique_index.Key_name}`")
    # full_name is still searched on (search_index), keep a plain index
    if not frappe.db.get_column_index("tabStudent", "full_name", unique=False):
        frappe.db.sql_ddl("ALTER TABLE `tabStudent` ADD INDEX `full_name_index` (`full_name`)")


def verify():
    """
    Read-only health check. Prints how many students still need renaming and,
    for every field linking to Student, how many values point to a Student
    that does not exist. Run before and after the migration: the broken-link
    counts must not grow.
    """
    total = frappe.db.count("Student")
    pending = frappe.db.sql(
        "SELECT COUNT(*) FROM `tabStudent` WHERE student_code IS NULL OR name != student_code"
    )[0][0]
    no_code = frappe.db.sql(
        "SELECT COUNT(*) FROM `tabStudent` WHERE IFNULL(student_code, '') = ''"
    )[0][0]
    dup_codes = frappe.db.sql(
        "SELECT COUNT(*) FROM (SELECT student_code FROM `tabStudent` "
        "WHERE IFNULL(student_code, '') != '' GROUP BY student_code HAVING COUNT(*) > 1) d"
    )[0][0]
    series = frappe.db.sql("SELECT current FROM `tabSeries` WHERE name = %s", SERIES_KEY)

    print(f"Students: {total}")
    print(f"  ID different from code (still to rename): {pending}")
    print(f"  Without code: {no_code}   Duplicate codes: {dup_codes}")
    print(f"  ALU- series counter: {series[0][0] if series else 'not created'}")
    print("Broken links (value points to a Student that doesn't exist):")

    broken_total = 0
    for lf in get_link_fields("Student"):
        if lf.get("issingle"):
            continue
        dt, field = lf["parent"], lf["fieldname"]
        if not frappe.db.table_exists(dt) or not frappe.db.has_column(dt, field):
            continue
        broken = frappe.db.sql(
            f"""
            SELECT COUNT(*) FROM `tab{dt}` t
            LEFT JOIN `tabStudent` s ON s.name = t.`{field}`
            WHERE IFNULL(t.`{field}`, '') != '' AND s.name IS NULL
            """
        )[0][0]
        if broken:
            broken_total += broken
            print(f"  {dt}.{field}: {broken}")
    print(f"  Total: {broken_total}")
