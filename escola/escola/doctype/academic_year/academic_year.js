// Copyright (c) 2024, EntreTech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Academic Year", {
	refresh(frm) {
		if (!frm.is_new() && frm.doc.is_active) {
			frm.dashboard.set_headline_alert(
				__("Este é o Ano Lectivo actual."),
				"green"
			);
		}
	},
});
