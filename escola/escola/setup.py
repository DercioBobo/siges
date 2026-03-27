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
}


def after_install():
    create_custom_fields()


def after_migrate():
    create_custom_fields()


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
