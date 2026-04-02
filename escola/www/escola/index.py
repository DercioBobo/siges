import frappe

no_cache = 1


def get_context(context):
    settings = frappe.get_single("School Settings")
    context.school_name = settings.school_name or "Escola"
    context.school_logo = settings.school_logo or ""
    context.school_address = settings.school_address or ""
    context.school_phone = settings.school_phone or ""
    context.school_email = settings.school_email or ""
    context.school_website = settings.school_website or ""
    context.current_academic_year = settings.current_academic_year or ""
    context.guardian_portal_enabled = int(settings.guardian_portal_enabled or 0)
    context.minimum_passing_grade = float(settings.minimum_passing_grade or 10)
    context.grading_scale_max = float(settings.grading_scale_max or 20)
    context.recurso_threshold = float(settings.recurso_threshold or 8)
    context.director_name = settings.director_name or ""
