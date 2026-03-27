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

