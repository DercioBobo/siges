"""
escola/auth.py

Post-login routing. `role_home_page` in hooks.py only applies to Website
Users; teachers are System Users, so Frappe would send them to /app. This
hook overrides the post-login destination for teacher accounts while leaving
the desk reachable (the portal sidebar links back to /app).
"""
import frappe

# Users with any of these roles keep the desk as their landing page,
# even if they are also linked to a Teacher record.
DESK_FIRST_ROLES = {"System Manager", "Diretor Escolar", "Secretaria Escolar"}


def on_session_creation(login_manager):
    user = login_manager.user
    if user in ("Administrator", "Guest"):
        return

    roles = set(frappe.get_roles(user))
    if "Professor" not in roles or roles & DESK_FIRST_ROLES:
        return

    if frappe.db.exists("Teacher", {"user_id": user, "is_active": 1}):
        frappe.local.response["home_page"] = "/portal-professor"
