"""
escola/setup.py

Called after install and after every bench migrate.
Creates custom fields on standard ERPNext DocTypes required for school billing linkage.
Safe to call multiple times — create_custom_fields is idempotent.
"""

import frappe


_CUSTOM_FIELDS = {
    "Sales Invoice": [
        {
            "fieldname": "escola_billing_cycle",
            "fieldtype": "Link",
            "options": "Billing Cycle",
            "label": "Ciclo de Facturação (Escola)",
            "insert_after": "remarks",
            "read_only": 1,
            "no_copy": 1,
            "in_standard_filter": 1,
            "search_index": 1,
        },
        {
            "fieldname": "escola_student",
            "fieldtype": "Link",
            "options": "Student",
            "label": "Aluno (Escola)",
            "insert_after": "escola_billing_cycle",
            "read_only": 1,
            "no_copy": 1,
            "in_standard_filter": 1,
            "search_index": 1,
        },
    ],
    "Customer": [
        {
            "fieldname": "escola_student",
            "fieldtype": "Link",
            "options": "Student",
            "label": "Aluno (Escola)",
            "insert_after": "customer_name",
            "read_only": 1,
            "no_copy": 1,
            "in_standard_filter": 1,
            "search_index": 1,
        },
    ],
    "Sales Invoice Item": [
        {
            "fieldname": "escola_is_penalty_line",
            "fieldtype": "Check",
            "label": "Linha de Multa (Escola)",
            "insert_after": "description",
            "default": "0",
            "read_only": 1,
            "no_copy": 1,
            "print_hide": 1,
        },
    ],
}


def after_install():
    create_custom_fields()


def after_migrate():
    create_custom_fields()
    _migrate_grade_entry_row_fields()


def _migrate_grade_entry_row_fields():
    """
    Idempotent post-schema migration: copy legacy `grade` values into `scores_json`.
    Runs after every migrate so it catches the case where the patch fired before
    schema sync had added the new columns.
    """
    import json

    def _col_exists(col):
        return bool(
            frappe.db.sql(
                "SHOW COLUMNS FROM `tabGrade Entry Row` LIKE %s", col, as_dict=True
            )
        )

    if not _col_exists("grade"):
        return
    if not _col_exists("scores_json") or not _col_exists("trimester_average"):
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
    if rows:
        frappe.db.commit()


def create_custom_fields():
    try:
        from frappe.custom.doctype.custom_field.custom_field import (
            create_custom_fields as frappe_create_custom_fields,
        )

        frappe_create_custom_fields(_CUSTOM_FIELDS, ignore_validate=True, update=True)
        frappe.db.commit()
    except Exception as e:
        frappe.log_error(
            title="Escola — custom fields setup failed",
            message=frappe.get_traceback(),
        )
