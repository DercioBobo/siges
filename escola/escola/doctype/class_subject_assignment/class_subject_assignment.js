// Copyright (c) 2024, EntreTech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Class Subject Assignment", {
	refresh(frm) {
		set_queries(frm);
	},

	class_group(frm) {
		if (!frm.doc.class_group) return;

		frappe.db
			.get_value("Class Group", frm.doc.class_group, [
				"academic_year",
				"school_class",
			])
			.then((r) => {
				if (!r.message) return;
				const { academic_year, school_class } = r.message;
				if (!frm.doc.academic_year && academic_year) {
					frm.set_value("academic_year", academic_year);
				}
				if (!frm.doc.school_class && school_class) {
					frm.set_value("school_class", school_class);
				}
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
	const cg_filters = { is_active: 1 };
	if (frm.doc.academic_year) cg_filters.academic_year = frm.doc.academic_year;
	if (frm.doc.school_class) cg_filters.school_class = frm.doc.school_class;

	frm.set_query("class_group", () => ({ filters: cg_filters }));
	frm.set_query("subject", () => ({ filters: { is_active: 1 } }));
	frm.set_query("teacher", () => ({ filters: { is_active: 1 } }));
}
