import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import formatdate, getdate


class ServicoExtra(Document):
    pass


@frappe.whitelist()
def update_price(doc_name, new_amount, motive):
    """Update the global price for a service and log the change."""
    doc = frappe.get_doc("Servico Extra", doc_name)
    old_amount = float(doc.current_amount or 0)
    new_amount = float(new_amount)

    doc.current_amount = new_amount

    ts = formatdate(getdate(), "dd/MM/yyyy")
    user = frappe.session.user
    entry = '{ts} | {old:,.2f} → {new:,.2f} MZN | "{motive}" | {user}'.format(
        ts=ts, old=old_amount, new=new_amount, motive=motive, user=user,
    )
    doc.price_history = (entry + "\n" + doc.price_history) if doc.price_history else entry

    doc.save(ignore_permissions=True)
    frappe.db.commit()

    return {"old_amount": old_amount, "new_amount": new_amount}
