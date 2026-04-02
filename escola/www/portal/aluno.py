import frappe

login_required = True
no_cache = 1


def get_context(context):
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/portal"
        raise frappe.Redirect

    if not frappe.db.get_single_value("School Settings", "guardian_portal_enabled"):
        frappe.local.flags.redirect_location = "/portal"
        raise frappe.Redirect

    guardian = frappe.db.get_value(
        "Guardian",
        {"user_id": frappe.session.user},
        ["name", "portal_access"],
        as_dict=True,
    )
    if not guardian or not guardian.portal_access:
        frappe.local.flags.redirect_location = "/portal"
        raise frappe.Redirect

    student = frappe.form_dict.get("s") or ""
    if not student:
        frappe.local.flags.redirect_location = "/portal"
        raise frappe.Redirect

    # Ownership check — guardian must own this student
    owner = frappe.db.get_value("Student", student, "primary_guardian")
    if owner != guardian.name:
        frappe.local.flags.redirect_location = "/portal"
        raise frappe.Redirect

    s = frappe.db.get_value(
        "Student", student,
        ["full_name", "current_school_class", "current_class_group", "current_status", "financial_status"],
        as_dict=True,
    )
    if not s:
        frappe.local.flags.redirect_location = "/portal"
        raise frappe.Redirect

    shift = ""
    if s.current_class_group:
        shift = frappe.db.get_value("Class Group", s.current_class_group, "shift") or ""

    settings = frappe.get_single("School Settings")
    context.school_name = settings.school_name or "Portal Escolar"
    context.school_logo = settings.school_logo or ""
    context.csrf_token = frappe.session.data.get("csrf_token", "")
    context.student = student
    context.student_full_name = s.full_name or student
    context.student_class = s.current_school_class or ""
    context.student_class_group = s.current_class_group or ""
    context.student_status = s.current_status or ""
    context.student_financial_status = s.financial_status or ""
    context.student_shift = shift
