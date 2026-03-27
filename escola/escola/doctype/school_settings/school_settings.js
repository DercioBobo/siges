// Copyright (c) 2024, EntreTech and contributors
// For license information, please see license.txt

frappe.ui.form.on("School Settings", {
	refresh(frm) {
		set_queries(frm);
	},

	current_academic_year(frm) {
		frm.set_value("current_academic_term", null);
		set_queries(frm);
	},

	default_company(frm) {
		// Clear income account when company changes to avoid mismatches
		frm.set_value("default_income_account", null);
		set_queries(frm);
	},
});

function set_queries(frm) {
	frm.set_query("current_academic_term", () => {
		const filters = {};
		if (frm.doc.current_academic_year) {
			filters.academic_year = frm.doc.current_academic_year;
		}
		return { filters };
	});

	frm.set_query("default_income_account", () => {
		const filters = { root_type: "Income", is_group: 0 };
		if (frm.doc.default_company) {
			filters.company = frm.doc.default_company;
		}
		return { filters };
	});

	frm.set_query("default_customer_group", () => ({
		filters: { is_group: 0 },
	}));
}
