// Copyright (c) 2024, EntreTech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Student Group Assignment", {
	refresh(frm) {
		set_queries(frm);
	},

	student(frm) {
		// Refresh enrollment filter when student changes
		frm.set_value("enrollment", null);
		frm.set_query("enrollment", () => ({
			filters: {
				student: frm.doc.student || "",
				enrollment_status: "Activa",
			},
		}));
	},

	enrollment(frm) {
		if (!frm.doc.enrollment) return;

		frappe.db
			.get_value("Student Enrollment", frm.doc.enrollment, [
				"student",
				"academic_year",
				"school_class",
			])
			.then((r) => {
				if (!r.message) return;
				const { student, academic_year, school_class } = r.message;
				frm.set_value("student", student);
				frm.set_value("academic_year", academic_year);
				frm.set_value("school_class", school_class);
			});
	},

	academic_year(frm) {
		frm.set_value("class_group", null);
		set_queries(frm);
	},

	school_class(frm) {
		frm.set_value("class_group", null);
		set_queries(frm);
	},
});

function set_queries(frm) {
	frm.set_query("enrollment", () => ({
		filters: {
			student: frm.doc.student || "",
			enrollment_status: "Activa",
		},
	}));

	const cg_filters = { is_active: 1 };
	if (frm.doc.academic_year) cg_filters.academic_year = frm.doc.academic_year;
	if (frm.doc.school_class) cg_filters.school_class = frm.doc.school_class;

	frm.set_query("class_group", () => ({ filters: cg_filters }));
}
