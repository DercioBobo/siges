import frappe


def get_context(context):
    if frappe.session.user != "Guest":
        frappe.local.login_manager.logout()
    frappe.local.flags.redirect_location = "/login"
    raise frappe.Redirect
