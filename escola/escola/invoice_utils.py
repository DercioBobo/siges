import frappe
from frappe import _


def invoice_success_msg(invoice_name, intro=""):
    """
    Return a standard success HTML string for msgprint when an individual
    invoice is created. Shows a form link and a direct print link.
    Any future flow that creates a single Sales Invoice should use this.
    """
    form_url  = f"/app/sales-invoice/{invoice_name}"
    print_url = f"/printview?doctype=Sales%20Invoice&name={invoice_name}&trigger_print=1"
    prefix    = f"{intro} " if intro else ""
    return (
        f"{prefix}Factura <b><a href='{form_url}'>{invoice_name}</a></b> criada. "
        f"&nbsp;<a href='{print_url}' target='_blank'>"
        f"<i class='fa fa-print'></i> {_('Imprimir')}</a>"
    )
