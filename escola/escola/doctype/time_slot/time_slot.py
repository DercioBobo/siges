import frappe
from frappe import _
from frappe.model.document import Document


class TimeSlot(Document):
    def validate(self):
        if self.start_time and self.end_time and self.start_time >= self.end_time:
            frappe.throw(_("A hora de início deve ser anterior à hora de fim."))
        if not self.sort_order:
            frappe.throw(_("Defina a Ordem de apresentação deste slot."))
