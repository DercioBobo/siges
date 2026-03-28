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
			frm.set_value("from_school_class", null);
			frm.set_value("from_class_group", null);
			frm.set_value("to_school_class", null);
			frm.set_value("to_class_group", null);
		} else if (t === _ENTRY) {
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
			fetch_active_assignment(frm);
		}
	},

	academic_year(frm) {
		frm.set_value("from_school_class", null);
		frm.set_value("from_class_group", null);
		frm.set_value("to_class_group", null);
		frm.set_value("entry_class_group", null);
		set_queries(frm);

		const t = frm.doc.transfer_type || _INTERNAL;
		if (frm.doc.student && (t === _INTERNAL || t === _EXIT)) {
			fetch_active_assignment(frm);
		}
	},

	from_class_group(frm) {
		// from_school_class will be fetched automatically via fetch_from
		set_queries(frm);
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
	frm.set_query("to_school_class", () => ({ filters: { is_active: 1 } }));

	const dest_filters = { is_active: 1 };
	if (frm.doc.academic_year) dest_filters.academic_year = frm.doc.academic_year;
	if (frm.doc.to_school_class) dest_filters.school_class = frm.doc.to_school_class;
	frm.set_query("to_class_group", () => ({ filters: dest_filters }));

	const from_filters = { is_active: 1 };
	if (frm.doc.academic_year) from_filters.academic_year = frm.doc.academic_year;
	frm.set_query("from_class_group", () => ({ filters: from_filters }));

	const entry_filters = { is_active: 1 };
	if (frm.doc.academic_year) entry_filters.academic_year = frm.doc.academic_year;
	frm.set_query("entry_class_group", () => ({ filters: entry_filters }));
}

function fetch_active_assignment(frm) {
	frappe.db
		.get_value(
			"Student Group Assignment",
			{ student: frm.doc.student, academic_year: frm.doc.academic_year, status: "Activa" },
			["class_group", "school_class"]
		)
		.then((r) => {
			if (!r.message || !r.message.class_group) return;
			const t = frm.doc.transfer_type || _INTERNAL;
			if (t === _INTERNAL) {
				frm.set_value("from_class_group", r.message.class_group);
				frm.set_value("from_school_class", r.message.school_class);
			}
		});
}
