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
        {
            "fieldname": "escola_mes_referencia",
            "fieldtype": "Select",
            "options": "\nJaneiro\nFevereiro\nMarço\nAbril\nMaio\nJunho\nJulho\nAgosto\nSetembro\nOutubro\nNovembro\nDezembro",
            "label": "Mês de Referência",
            "insert_after": "escola_student",
            "read_only": 1,
            "no_copy": 1,
            "in_standard_filter": 1,
        },
        {
            "fieldname": "escola_encarregado",
            "fieldtype": "Link",
            "options": "Guardian",
            "label": "Encarregado (Escola)",
            "insert_after": "escola_mes_referencia",
            "fetch_from": "escola_student.primary_guardian",
            "read_only": 1,
            "no_copy": 1,
            "in_standard_filter": 1,
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
    create_default_items()
    create_portal_roles()


def after_migrate():
    create_custom_fields()
    create_default_items()
    create_portal_roles()


_PORTAL_ROLES = [
    {"role_name": "Encarregado de Educação", "desk_access": 0},
    {"role_name": "Aluno", "desk_access": 0},
]


def create_portal_roles():
    """Idempotently create roles used for the parent/student portal."""
    try:
        for role_def in _PORTAL_ROLES:
            if not frappe.db.exists("Role", role_def["role_name"]):
                frappe.get_doc({"doctype": "Role", **role_def}).insert(ignore_permissions=True)
        frappe.db.commit()
    except Exception:
        frappe.log_error(
            title="Escola — criação de roles do portal falhou",
            message=frappe.get_traceback(),
        )


_DEFAULT_ITEMS = [
    {
        "item_code": "Propina",
        "item_name": "Propina",
        "description": "Propina escolar.",
    },
    {
        "item_code": "Multa por Atraso",
        "item_name": "Multa por Atraso",
        "description": "Multa por atraso no pagamento de propinas escolares.",
    },
]


def create_default_items():
    """Idempotently create default ERPNext Items used by the escola module."""
    try:
        groups = frappe.get_all("Item Group", filters={"is_group": 0}, fields=["name"], limit=1)
        item_group = groups[0].name if groups else "All Item Groups"

        for item_def in _DEFAULT_ITEMS:
            if frappe.db.exists("Item", item_def["item_code"]):
                continue
            frappe.get_doc({
                "doctype": "Item",
                "item_code": item_def["item_code"],
                "item_name": item_def["item_name"],
                "item_group": item_group,
                "is_stock_item": 0,
                "include_item_in_manufacturing": 0,
                "description": item_def["description"],
            }).insert(ignore_permissions=True)

        frappe.db.commit()
    except Exception:
        frappe.log_error(
            title="Escola — default items setup failed",
            message=frappe.get_traceback(),
        )


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
