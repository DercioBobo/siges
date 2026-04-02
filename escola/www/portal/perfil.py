import frappe

login_required = True
no_cache = 1


def get_context(context):
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/portal/perfil"
        raise frappe.Redirect

    if not frappe.db.get_single_value("School Settings", "guardian_portal_enabled"):
        frappe.local.flags.redirect_location = "/portal"
        raise frappe.Redirect

    guardian = frappe.db.get_value(
        "Guardian",
        {"user_id": frappe.session.user},
        ["name", "full_name", "phone", "alternative_phone", "email", "address", "portal_access"],
        as_dict=True,
    )
    if not guardian or not guardian.portal_access:
        frappe.local.flags.redirect_location = "/portal"
        raise frappe.Redirect

    settings = frappe.get_single("School Settings")
    context.school_name = settings.school_name or "Portal Escolar"
    context.school_logo = settings.school_logo or ""
    context.guardian = guardian
