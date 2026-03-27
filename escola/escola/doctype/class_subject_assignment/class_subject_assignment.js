// Copyright (c) 2024, EntreTech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Class Subject Assignment", {
	refresh(frm) {
		set_queries(frm);
	},

	school_class(frm) {
		set_queries(frm);
	},
});

function set_queries(frm) {
	frm.set_query("subject", () => ({ filters: { is_active: 1 } }));
	frm.set_query("teacher", () => ({ filters: { is_active: 1 } }));
}
