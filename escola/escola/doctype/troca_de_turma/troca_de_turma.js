// Copyright (c) 2024, EntreTech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Troca De Turma", {
	onload(frm) {
		escola.utils.auto_fill_academic_year(frm);
	},

	refresh(frm) {
		_set_queries(frm);
		if (frm.doc.docstatus === 0) {
			_check_class_change(frm);
		}
	},

	student(frm) {
		if (frm.doc.student && frm.doc.academic_year) {
			_fetch_active_group(frm);
		}
	},

	academic_year(frm) {
		frm.set_value("from_class_group", null);
		frm.set_value("to_class_group", null);
		_set_queries(frm);
		if (frm.doc.student && frm.doc.academic_year) {
			_fetch_active_group(frm);
		}
	},

	from_class_group(frm) {
		frm.set_value("to_class_group", null);
		_set_queries(frm);
		frm.set_intro("");
		frm.set_df_property("reason", "reqd", 0);
		// If academic_year is still empty, fill it from the chosen turma
		// without triggering the academic_year handler (which would clear from_class_group)
		if (frm.doc.from_class_group && !frm.doc.academic_year) {
			frappe.db.get_value("Class Group", frm.doc.from_class_group, "academic_year")
				.then(r => {
					const yr = r.message && r.message.academic_year;
					if (yr && !frm.doc.academic_year) {
						frm.doc.academic_year = yr;
						frm.refresh_field("academic_year");
					}
				});
		}
	},

	to_class_group(frm) {
		_set_queries(frm);
		_check_class_change(frm);
	},
});

// ---------------------------------------------------------------------------

function _set_queries(frm) {
	const from_f = { is_active: 1 };
	if (frm.doc.academic_year) from_f.academic_year = frm.doc.academic_year;
	frm.set_query("from_class_group", () => ({ filters: from_f }));

	const to_f = { is_active: 1 };
	if (frm.doc.academic_year) to_f.academic_year = frm.doc.academic_year;
	if (frm.doc.from_class_group) to_f.name = ["!=", frm.doc.from_class_group];
	frm.set_query("to_class_group", () => ({ filters: to_f }));
}

async function _check_class_change(frm) {
	if (!frm.doc.from_class_group || !frm.doc.to_class_group) {
		frm.set_intro("");
		frm.set_df_property("reason", "reqd", 0);
		return;
	}

	const [from_r, to_r] = await Promise.all([
		frappe.db.get_value("Class Group", frm.doc.from_class_group, "school_class"),
		frappe.db.get_value("Class Group", frm.doc.to_class_group,   "school_class"),
	]);

	const from_sc = from_r.message && from_r.message.school_class;
	const to_sc   = to_r.message   && to_r.message.school_class;
	const cross   = from_sc && to_sc && from_sc !== to_sc;

	if (cross) {
		frm.set_intro(
			__("Atenção: esta troca envolve uma mudança de classe ({0} → {1}). O motivo é obrigatório.",
				[from_sc, to_sc]),
			"orange"
		);
		frm.set_df_property("reason", "reqd", 1);
	} else {
		frm.set_intro("");
		frm.set_df_property("reason", "reqd", 0);
	}
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
