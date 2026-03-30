// Copyright (c) 2024, EntreTech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Academic Term", {
	onload(frm) {
		escola.utils.auto_fill_academic_year(frm);
	},

	academic_year(frm) {
		// Suggest date range from academic year to help the user
		if (!frm.doc.academic_year) return;

		frappe.db
			.get_value("Academic Year", frm.doc.academic_year, [
				"start_date",
				"end_date",
			])
			.then((r) => {
				if (!r.message) return;
				const { start_date, end_date } = r.message;
				if (!frm.doc.start_date && start_date) {
					frm.set_value("start_date", start_date);
				}
				if (!frm.doc.end_date && end_date) {
					frm.set_value("end_date", end_date);
				}
			});
	},
});
