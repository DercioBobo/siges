import frappe

login_required = True
no_cache = 1


def get_context(context):
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/portal-professor"
        raise frappe.Redirect

    teacher = frappe.db.get_value(
        "Teacher",
        {"user_id": frappe.session.user},
        ["name", "full_name", "teacher_code", "is_active"],
        as_dict=True,
    )

    if not teacher or not teacher.is_active:
        context.access_denied = True
        return

    settings = frappe.get_single("School Settings")
    context.school_name       = settings.school_name or "Portal do Professor"
    context.school_logo       = settings.school_logo or ""
    context.teacher_full_name = teacher.full_name or ""
    context.teacher_code      = teacher.teacher_code or ""
    context.csrf_token        = frappe.session.data.get("csrf_token", "")
    context.min_passing_grade = float(settings.minimum_passing_grade or 10)
    context.grading_scale_max = float(settings.grading_scale_max or 20)
