"""
Migrate Grade Entry Row: copy legacy `grade` Float column into `scores_json`
and populate `trimester_average` / `is_approved` from the old value.

Idempotent: re-running always writes from `grade`, which is harmless.
Skips silently when the old `grade` column no longer exists (already dropped)
or when the new `scores_json` column has not yet been added by schema sync.
"""
import json

import frappe


def _col_exists(table, column):
    return bool(
        frappe.db.sql(
            f"SHOW COLUMNS FROM `{table}` LIKE %s", column, as_dict=True
        )
    )


def execute():
    # Old column must still be present
    if not _col_exists("tabGrade Entry Row", "grade"):
        return

    # New columns must have been added by schema sync already
    if not _col_exists("tabGrade Entry Row", "scores_json"):
        return
    if not _col_exists("tabGrade Entry Row", "trimester_average"):
        return

    rows = frappe.db.sql(
        "SELECT name, grade FROM `tabGrade Entry Row` WHERE grade IS NOT NULL",
        as_dict=True,
    )

    for row in rows:
        frappe.db.sql(
            """UPDATE `tabGrade Entry Row`
               SET scores_json       = %s,
                   trimester_average = %s,
                   is_approved       = %s
               WHERE name = %s""",
            (
                json.dumps({"Avaliação": row.grade}),
                row.grade,
                1 if (row.grade or 0) >= 10 else 0,
                row.name,
            ),
        )

    frappe.db.commit()
