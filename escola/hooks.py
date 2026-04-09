from . import __version__ as app_version

app_name = "escola"
app_title = "Escola"
app_publisher = "EntreTech"
app_description = "Sistema de Gestão Escolar"
app_email = "info@entretech.co.mz"
app_license = "MIT"
app_version = app_version

# -----------------------------------------------------------------
# Required roles — created on install
# -----------------------------------------------------------------
# These are defined via Role DocType records in fixtures if needed.
# For now roles are created manually or via the Role DocType.

# -----------------------------------------------------------------
# DocType permissions are embedded in each DocType JSON.
# -----------------------------------------------------------------

# -----------------------------------------------------------------
# Post-install and post-migrate hooks
# Creates custom fields on ERPNext standard DocTypes for billing linkage.
# -----------------------------------------------------------------
after_install = "escola.escola.setup.after_install"
after_migrate = ["escola.escola.setup.after_migrate"]

# -----------------------------------------------------------------
# Document event hooks
# -----------------------------------------------------------------
doc_events = {
    "Student": {
        # Keep student_name in sync on every Class Group roster row
        "on_update": "escola.escola.doctype.class_group.class_group.sync_student_in_rosters",
    },
    "Sales Invoice": {
        # Recalculate student financial_status whenever a payment is applied or invoice changes
        "on_update_after_submit": "escola.escola.doctype.billing_cycle.penalty.on_sales_invoice_update",
        "on_cancel":              "escola.escola.doctype.billing_cycle.penalty.on_sales_invoice_update",
    },
    "Annual Assessment": {
        # Auto-generate/update Report Cards whenever assessment rows are saved
        "on_update": "escola.escola.doctype.report_card.report_card.generate_for_assessment_hook",
    },
}

# -----------------------------------------------------------------
# Fixtures — export School Settings with the app so configuration
# is version-controlled alongside the code.
# -----------------------------------------------------------------
fixtures = [
    {"dt": "School Settings"},
]

# -----------------------------------------------------------------
# App includes — kept minimal
# -----------------------------------------------------------------
# app_include_css = []
app_include_js = ["/assets/escola/js/escola_utils.js"]

# -----------------------------------------------------------------
# Website
# -----------------------------------------------------------------
# website_route_rules = []

# Redirect portal-only users to their respective portals after login
# instead of the desk (which they have no access to).
role_home_page = {
    "Encarregado de Educação": "/portal",
    "Professor": "/portal-professor",
}

# -----------------------------------------------------------------
# Scheduled tasks
# -----------------------------------------------------------------
scheduler_events = {
    # Recalculate financial_status for every student with outstanding invoices.
    # Catches time-based transitions (e.g. due date crossed overnight).
    "daily": [
        "escola.escola.doctype.billing_cycle.penalty.update_all_student_financial_statuses",
        "escola.escola.doctype.billing_cycle.penalty.apply_all_pending_penalties",
        "escola.escola.doctype.student.student.update_all_student_ages",
        "escola.escola.doctype.billing_schedule.billing_schedule.run_due_schedules",
        "escola.escola.doctype.report_card.report_card.refresh_all_report_cards",
    ],
}

# -----------------------------------------------------------------
# Jinja customizations — not used yet
# -----------------------------------------------------------------
# jinja = {}
