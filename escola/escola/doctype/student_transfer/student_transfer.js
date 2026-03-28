// Copyright (c) 2024, EntreTech and contributors
// For license information, please see license.txt

const _INTERNAL = "Interna (Entre Turmas)";
const _EXIT     = "Saída (Para Outra Escola)";
const _ENTRY    = "Entrada (Outra Escola)";

frappe.ui.form.on("Student Transfer", {
	refresh(frm) {
		set_queries(frm);
	},

	transfer_type(frm) {
		// Clear type-specific fields when switching
		const t = frm.doc.transfer_type;
		if (t === _INTERNAL) {
			frm.set_value("origin_school", null);
			frm.set_value("origin_city", null);
			frm.set_value("origin_class", null);
			frm.set_value("origin_grades", null);
			frm.set_value("entry_class_group", null);
			frm.set_value("destination_school", null);
			frm.set_value("destination_city", null);
			frm.set_value("exit_reason", null);
			frm.set_value("exit_reason_detail", null);
		} else if (t === _EXIT) {
			frm.set_value("origin_school", null);
			frm.set_value("origin_city", null);
			frm.set_value("origin_class", null);
			frm.set_value("origin_grades", null);
			frm.set_value("entry_class_group", null);
			frm.set_value("from_enrollment", null);
			frm.set_value("from_school_class", null);
			frm.set_value("from_class_group", null);
			frm.set_value("to_school_class", null);
			frm.set_value("to_class_group", null);
		} else if (t === _ENTRY) {
			frm.set_value("from_enrollment", null);
			frm.set_value("from_school_class", null);
			frm.set_value("from_class_group", null);
			frm.set_value("to_school_class", null);
			frm.set_value("to_class_group", null);
			frm.set_value("destination_school", null);
			frm.set_value("destination_city", null);
			frm.set_value("exit_reason", null);
			frm.set_value("exit_reason_detail", null);
		}
		set_queries(frm);
	},

	student(frm) {
		if (!frm.doc.student || !frm.doc.academic_year) return;
		const t = frm.doc.transfer_type || _INTERNAL;
		if (t === _INTERNAL || t === _EXIT) {
			fetch_active_enrollment_and_assignment(frm);
		}
	},

	academic_year(frm) {
		frm.set_value("from_enrollment", null);
		frm.set_value("from_school_class", null);
		frm.set_value("from_class_group", null);
		frm.set_value("to_class_group", null);
		frm.set_value("entry_class_group", null);
		set_queries(frm);

		const t = frm.doc.transfer_type || _INTERNAL;
		if (frm.doc.student && (t === _INTERNAL || t === _EXIT)) {
			fetch_active_enrollment_and_assignment(frm);
		}
	},

	from_enrollment(frm) {
		if (!frm.doc.from_enrollment) return;
		frappe.db
			.get_value("Student Enrollment", frm.doc.from_enrollment, ["school_class"])
			.then((r) => {
				if (r.message && r.message.school_class) {
					frm.set_value("from_school_class", r.message.school_class);
				}
			});
	},

	to_school_class(frm) {
		frm.set_value("to_class_group", null);
		set_queries(frm);
	},
});

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function set_queries(frm) {
	// from_enrollment: only active enrollments for this student + year
	frm.set_query("from_enrollment", () => ({
		filters: {
			student: frm.doc.student || "",
			academic_year: frm.doc.academic_year || "",
			enrollment_status: "Activa",
		},
	}));

	// to_school_class
	frm.set_query("to_school_class", () => ({ filters: { is_active: 1 } }));

	// to_class_group: filtered by year + optional school_class
	const dest_filters = { is_active: 1 };
	if (frm.doc.academic_year) dest_filters.academic_year = frm.doc.academic_year;
	if (frm.doc.to_school_class) dest_filters.school_class = frm.doc.to_school_class;
	frm.set_query("to_class_group", () => ({ filters: dest_filters }));

	// from_class_group: filtered by year + from_school_class
	const from_filters = { is_active: 1 };
	if (frm.doc.academic_year) from_filters.academic_year = frm.doc.academic_year;
	if (frm.doc.from_school_class) from_filters.school_class = frm.doc.from_school_class;
	frm.set_query("from_class_group", () => ({ filters: from_filters }));

	// entry_class_group: filtered by year
	const entry_filters = { is_active: 1 };
	if (frm.doc.academic_year) entry_filters.academic_year = frm.doc.academic_year;
	frm.set_query("entry_class_group", () => ({ filters: entry_filters }));
}

function fetch_active_enrollment_and_assignment(frm) {
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

			const t = frm.doc.transfer_type || _INTERNAL;
			if (t === _INTERNAL) {
				frm.set_value("from_enrollment", r.message.name);
				frm.set_value("from_school_class", r.message.school_class);
			}

			// Fetch active assignment regardless of type (useful for both internal and exit)
			frappe.db
				.get_value(
					"Student Group Assignment",
					{student: frm.doc.student, academic_year: frm.doc.academic_year, status: "Activa"},
					["class_group"]
				)
				.then((ra) => {
					if (ra.message && ra.message.class_group && t === _INTERNAL) {
						frm.set_value("from_class_group", ra.message.class_group);
					}
				});
		});
}
