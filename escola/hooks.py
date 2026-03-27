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
# app_include_js = []

# -----------------------------------------------------------------
# Website — not used yet
# -----------------------------------------------------------------
# website_route_rules = []

# -----------------------------------------------------------------
# Scheduled tasks — not used yet
# -----------------------------------------------------------------
# scheduler_events = {}

# -----------------------------------------------------------------
# Jinja customizations — not used yet
# -----------------------------------------------------------------
# jinja = {}
