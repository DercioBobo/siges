import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate


class AcademicYear(Document):
    def validate(self):
        self._validate_dates()
        if self.is_active:
            self._ensure_single_active()

    def _validate_dates(self):
        if self.start_date and self.end_date:
            if getdate(self.end_date) <= getdate(self.start_date):
                frappe.throw(
                    _("A Data de Fim deve ser posterior à Data de Início."),
                    title=_("Datas inválidas"),
                )

    def _ensure_single_active(self):
        existing = frappe.db.get_value(
            "Academic Year",
            {"is_active": 1, "name": ("!=", self.name)},
            "year_name",
        )
        if existing:
            frappe.throw(
                _("O ano lectivo <b>{0}</b> já está marcado como Ano Actual. "
                  "Desactive-o primeiro antes de activar este.").format(existing),
                title=_("Ano Actual duplicado"),
            )


@frappe.whitelist()
def create_terms(academic_year, terms):
    """Bulk-create Academic Terms for a year (used by the Criar Trimestres dialog)."""
    if isinstance(terms, str):
        terms = json.loads(terms)

    if not frappe.db.exists("Academic Year", academic_year):
        frappe.throw(_("Ano Lectivo <b>{0}</b> não encontrado.").format(academic_year))
    frappe.has_permission("Academic Term", "create", throw=True)

    for t in terms:
        if not (t.get("term_name") or "").strip() or not t.get("start_date") or not t.get("end_date"):
            frappe.throw(_("Preencha o nome e as datas de todos os períodos."))
        if getdate(t["end_date"]) <= getdate(t["start_date"]):
            frappe.throw(
                _("A Data de Fim deve ser posterior à Data de Início no período <b>{0}</b>.").format(
                    t["term_name"]
                ),
                title=_("Datas inválidas"),
            )

    created, skipped = [], []
    for t in terms:
        name = t["term_name"].strip()
        if frappe.db.exists("Academic Term", name):
            skipped.append(name)
            continue
        doc = frappe.get_doc({
            "doctype": "Academic Term",
            "term_name": name,
            "academic_year": academic_year,
            "start_date": t["start_date"],
            "end_date": t["end_date"],
            "is_active": 1,
        }).insert()
        created.append(doc.name)

    return {"created": created, "skipped": skipped}
