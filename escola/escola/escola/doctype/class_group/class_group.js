// Copyright (c) 2024, EntreTech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Class Group", {
	// Filter Teacher link to active teachers only
	refresh(frm) {
		frm.set_query("class_teacher", () => ({
			filters: { is_active: 1 },
		}));
	},
});
