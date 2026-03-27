"""
Migrate Grade Entry Row: copy legacy `grade` Float column into `scores_json`
and set `trimester_average` from the old value.

Safe to run multiple times (idempotent): skips rows where scores_json is
already populated.
"""
import json

import frappe


def execute():
    # Only proceed if the old `grade` column still exists in the table
    columns = frappe.db.sql(
        "SHOW COLUMNS FROM `tabGrade Entry Row` LIKE 'grade'", as_dict=True
    )
    if not columns:
        return  # already migrated or column never existed

    rows = frappe.db.sql(
        """
        SELECT name, grade
        FROM `tabGrade Entry Row`
        WHERE (scores_json IS NULL OR scores_json = '')
          AND grade IS NOT NULL
        """,
        as_dict=True,
    )

    for row in rows:
        scores = {"Avaliação": row.grade}
        frappe.db.sql(
            """
            UPDATE `tabGrade Entry Row`
            SET scores_json = %s,
                trimester_average = %s,
                is_approved = %s
            WHERE name = %s
            """,
            (
                json.dumps(scores),
                row.grade,
                1 if (row.grade or 0) >= 10 else 0,
                row.name,
            ),
        )

    frappe.db.commit()
