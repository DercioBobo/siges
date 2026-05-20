import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import formatdate, get_last_day, getdate


class MensalidadeExtraDoAluno(Document):
    def validate(self):
        existing = frappe.db.get_value(
            "Mensalidade Extra do Aluno",
            {"student": self.student, "name": ("!=", self.name)},
            "name",
        )
        if existing:
            frappe.throw(
                _("Já existe um registo de Mensalidade Extra para o aluno {0}: {1}").format(
                    self.student, existing
                ),
                title=_("Registo duplicado"),
            )

        seen = set()
        for row in self.services or []:
            if row.status == "Activo":
                if row.service in seen:
                    frappe.throw(
                        _("O serviço <b>{0}</b> está duplicado como Activo. "
                          "Cancele a linha anterior antes de adicionar novamente.").format(row.service),
                        title=_("Serviço duplicado"),
                    )
                seen.add(row.service)


@frappe.whitelist()
def cancel_services(doc_name, services, motive):
    """
    Cancel selected service rows: sets status=Cancelado, end_date=last day of current month.
    Appends a timestamped entry to change_log.
    services: JSON list of child row names.
    """
    doc = frappe.get_doc("Mensalidade Extra do Aluno", doc_name)

    if isinstance(services, str):
        services = json.loads(services)

    end_date = get_last_day(getdate())
    ts = formatdate(getdate(), "dd/MM/yyyy")
    user = frappe.session.user
    log_lines = []

    for row in doc.services:
        if row.name in services and row.status == "Activo":
            row.status = "Cancelado"
            row.end_date = end_date
            service_name = frappe.db.get_value("Serviço Extra", row.service, "service_name") or row.service
            log_lines.append(
                '{ts} | CANCELADO: {svc} | "{motive}" | {user}'.format(
                    ts=ts, svc=service_name, motive=motive, user=user,
                )
            )

    if log_lines:
        new_entries = "\n".join(log_lines)
        doc.change_log = (new_entries + "\n" + doc.change_log) if doc.change_log else new_entries
        doc.save(ignore_permissions=True)
        frappe.db.commit()

    return {"cancelled": len(log_lines)}


@frappe.whitelist()
def get_active_services_for_student(student):
    """
    Return active service lines for a student, joined with master amounts.
    A row is active when: status=Activo, start_date <= today, end_date IS NULL or >= today.
    """
    today = getdate()

    mea_name = frappe.db.get_value("Mensalidade Extra do Aluno", {"student": student}, "name")
    if not mea_name:
        return []

    rows = frappe.db.sql(
        """
        SELECT
            l.name        AS row_name,
            l.service,
            se.service_name,
            se.current_amount,
            l.start_date,
            l.end_date
        FROM `tabLinha de Mensalidade Extra` l
        JOIN `tabServiço Extra` se ON se.name = l.service
        WHERE l.parent = %s
          AND l.status = 'Activo'
          AND l.start_date <= %s
          AND (l.end_date IS NULL OR l.end_date >= %s)
        ORDER BY se.service_name
        """,
        (mea_name, today, today),
        as_dict=True,
    )

    for r in rows:
        r["current_amount"] = float(r["current_amount"] or 0)
        if r["start_date"]:
            r["start_date"] = str(r["start_date"])
        if r["end_date"]:
            r["end_date"] = str(r["end_date"])

    return rows
