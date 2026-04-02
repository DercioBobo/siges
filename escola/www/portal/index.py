import frappe

login_required = True
no_cache = 1


def get_context(context):
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/portal"
        raise frappe.Redirect

    portal_enabled = frappe.db.get_single_value("School Settings", "guardian_portal_enabled")
    if not portal_enabled:
        context.portal_disabled = True
        return

    guardian = frappe.db.get_value(
        "Guardian",
        {"user_id": frappe.session.user},
        ["name", "full_name", "portal_access"],
        as_dict=True,
    )
    if not guardian or not guardian.portal_access:
        context.access_denied = True
        return

    settings = frappe.get_single("School Settings")
    context.school_name = settings.school_name or "Portal Escolar"
    context.school_logo = settings.school_logo or ""
    context.guardian_full_name = guardian.full_name or ""
    context.csrf_token = frappe.session.data.get("csrf_token", "")
