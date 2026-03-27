import frappe


def get_school_settings():
    """Return the School Settings singleton.

    Usage::

        from escola.escola import get_school_settings
        settings = get_school_settings()
        passing = settings.minimum_passing_grade or 10
    """
    return frappe.get_single("School Settings")
