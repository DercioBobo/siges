// Copyright (c) 2024, EntreTech and contributors
// For license information, please see license.txt

frappe.ui.form.on("School Class", {
	refresh(frm) {
		frm.set_query("default_teacher", () => ({
			filters: { is_active: 1 },
		}));
	},

	teaching_model(frm) {
		// Clear default_teacher when switching away from single-teacher model
		if (frm.doc.teaching_model !== "Professor Único") {
			frm.set_value("default_teacher", null);
		}
	},
});
