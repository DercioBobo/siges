// Copyright (c) 2024, EntreTech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Student Enrollment", {
	refresh(frm) {
		frm.set_query("school_class", () => ({
			filters: { is_active: 1 },
		}));
	},

	student(frm) {
		if (!frm.doc.student) return;

		frappe.db
			.get_value("Student", frm.doc.student, [
				"primary_guardian",
				"enrollment_type",
			])
			.then((r) => {
				if (!r.message) return;
				const { primary_guardian, enrollment_type } = r.message;
				if (!frm.doc.primary_guardian && primary_guardian) {
					frm.set_value("primary_guardian", primary_guardian);
				}
				if (!frm.doc.enrollment_type && enrollment_type) {
					frm.set_value("enrollment_type", enrollment_type);
				}
			});
	},
});
