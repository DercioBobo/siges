"""
escola/portal.py

Shared utilities for provisioning Frappe portal users for Guardians and Teachers.
Called from guardian.py and teacher.py after_insert hooks.
"""

import secrets
import frappe
from frappe import _
from frappe.utils.password import update_password


def _generate_temp_password():
    """Return a human-readable temp password like Escola@4728."""
    digits = "".join(str(secrets.randbelow(10)) for _ in range(4))
    return "Escola@" + digits


def _portal_email(doc):
    """Return the email to use as Frappe username. Falls back to a synthetic address."""
    email = (getattr(doc, "email", "") or "").strip()
    if email:
        return email
    # Synthetic internal address — not a real mailbox
    code = doc.name.lower().replace("-", "").replace(" ", "")
    return f"{code}@portal.escola"


def provision_portal_user(doc, role):
    """
    Idempotently create a Frappe User for the given doc and assign a temp password.
    Stores user_id and portal_password back on the doc (via db.set_value, no re-save).
    Safe to call multiple times — does nothing if user_id already set.
    """
    if doc.user_id:
        return

    email = _portal_email(doc)
    temp_pw = _generate_temp_password()

    if frappe.db.exists("User", email):
        user = frappe.get_doc("User", email)
    else:
        user = frappe.new_doc("User")
        user.email = email
        user.first_name = getattr(doc, "first_name", None) or doc.full_name or doc.name
        user.last_name = getattr(doc, "last_name", "") or ""
        user.send_welcome_email = 0
        user.enabled = 1
        user.insert(ignore_permissions=True)

    # Assign role if missing
    existing_roles = [r.role for r in user.get("roles", [])]
    if role not in existing_roles:
        user.append("roles", {"role": role})
        user.save(ignore_permissions=True)

    # Set temp password via the secure Frappe helper
    update_password(user.name, temp_pw)

    # Write back to the parent doc without touching modified timestamp
    frappe.db.set_value(
        doc.doctype,
        doc.name,
        {"user_id": user.name, "portal_password": temp_pw},
        update_modified=False,
    )


@frappe.whitelist()
def regenerate_password(doctype, name):
    """
    Generate a new temp password for the portal user linked to the given doc.
    Returns True on success so the JS caller can confirm and reload.
    """
    if doctype not in ("Guardian", "Teacher"):
        frappe.throw(_("DocType não suportado."))

    frappe.has_permission(doctype, "write", name, throw=True)

    user_id = frappe.db.get_value(doctype, name, "user_id")
    if not user_id:
        frappe.throw(_("Este registo não tem um utilizador do portal associado."))

    temp_pw = _generate_temp_password()
    update_password(user_id, temp_pw)

    frappe.db.set_value(doctype, name, "portal_password", temp_pw, update_modified=False)
    return True
