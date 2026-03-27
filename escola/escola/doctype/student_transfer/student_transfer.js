// Copyright (c) 2024, EntreTech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Student Transfer", {
	refresh(frm) {
		set_destination_query(frm);

		frm.set_query("from_enrollment", () => ({
			filters: {
				student: frm.doc.student || "",
				academic_year: frm.doc.academic_year || "",
				enrollment_status: "Activa",
			},
		}));

		frm.set_query("to_school_class", () => ({
			filters: { is_active: 1 },
		}));
	},

	student(frm) {
		if (!frm.doc.student || !frm.doc.academic_year) return;
		fetch_active_enrollment_and_assignment(frm);
	},

	academic_year(frm) {
		// Reset origin fields when year changes
		frm.set_value("from_enrollment", null);
		frm.set_value("from_school_class", null);
		frm.set_value("from_class_group", null);
		frm.set_value("to_class_group", null);
		set_destination_query(frm);

		if (frm.doc.student) {
			fetch_active_enrollment_and_assignment(frm);
		}
	},

	from_enrollment(frm) {
		if (!frm.doc.from_enrollment) return;

		frappe.db
			.get_value("Student Enrollment", frm.doc.from_enrollment, [
				"school_class",
			])
			.then((r) => {
				if (r.message && r.message.school_class) {
					frm.set_value("from_school_class", r.message.school_class);
				}
			});
	},

	to_school_class(frm) {
		frm.set_value("to_class_group", null);
		set_destination_query(frm);
	},
});

function fetch_active_enrollment_and_assignment(frm) {
	// Fetch active enrollment
	frappe.db
		.get_value(
			"Student Enrollment",
			{
				student: frm.doc.student,
				academic_year: frm.doc.academic_year,
				enrollment_status: "Activa",
			},
			["name", "school_class"]
		)
		.then((r) => {
			if (!r.message || !r.message.name) return;
			frm.set_value("from_enrollment", r.message.name);
			frm.set_value("from_school_class", r.message.school_class);

			// Now fetch active assignment
			frappe.db
				.get_value(
					"Student Group Assignment",
					{
						student: frm.doc.student,
						academic_year: frm.doc.academic_year,
						status: "Activa",
					},
					["class_group"]
				)
				.then((ra) => {
					if (ra.message && ra.message.class_group) {
						frm.set_value("from_class_group", ra.message.class_group);
					}
				});
		});
}

function set_destination_query(frm) {
	const filters = { is_active: 1 };
	if (frm.doc.academic_year) filters.academic_year = frm.doc.academic_year;
	if (frm.doc.to_school_class) filters.school_class = frm.doc.to_school_class;

	frm.set_query("to_class_group", () => ({ filters }));
}
