// Copyright (c) 2024, EntreTech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Student Transfer", {
	onload(frm) {
		escola.utils.auto_fill_academic_year(frm);
	},

	refresh(frm) {
		_set_queries(frm);
	},

	student(frm) {
		if (frm.doc.student && frm.doc.academic_year) {
			_fetch_active_group(frm);
		}
	},

	academic_year(frm) {
		frm.set_value("from_class_group", null);
		_set_queries(frm);
		if (frm.doc.student && frm.doc.academic_year) {
			_fetch_active_group(frm);
		}
	},

	from_class_group(frm) {
		_set_queries(frm);
	},
});

// ---------------------------------------------------------------------------

function _set_queries(frm) {
	const f = { is_active: 1 };
	if (frm.doc.academic_year) f.academic_year = frm.doc.academic_year;
	frm.set_query("from_class_group", () => ({ filters: f }));
}

function _fetch_active_group(frm) {
	frappe.db
		.get_value(
			"Student Group Assignment",
			{
				student: frm.doc.student,
				academic_year: frm.doc.academic_year,
				status: "Activa",
			},
			["class_group", "school_class"]
		)
		.then((r) => {
			if (!r.message || !r.message.class_group) return;
			if (!frm.doc.from_class_group) {
				frm.set_value("from_class_group", r.message.class_group);
			}
		});
}
