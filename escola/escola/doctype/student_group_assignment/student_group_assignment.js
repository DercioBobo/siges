// Copyright (c) 2024, EntreTech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Student Group Assignment", {
	refresh(frm) {
		set_queries(frm);
	},

	student(frm) {
		// When student changes, reset turma selection
		frm.set_value("class_group", null);
		frm.set_value("school_class", null);
		frm.set_value("academic_year", null);
		set_queries(frm);
	},

	class_group(frm) {
		// Clear derived fields so fetch_from can repopulate them
		frm.set_value("school_class", null);
		frm.set_value("academic_year", null);
	},

	academic_year(frm) {
		set_queries(frm);
	},

	school_class(frm) {
		set_queries(frm);
	},
});

function set_queries(frm) {
	const cg_filters = { is_active: 1 };
	if (frm.doc.academic_year) cg_filters.academic_year = frm.doc.academic_year;
	if (frm.doc.school_class) cg_filters.school_class = frm.doc.school_class;

	frm.set_query("class_group", () => ({ filters: cg_filters }));
}
