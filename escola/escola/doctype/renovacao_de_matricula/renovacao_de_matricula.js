// Copyright (c) 2024, EntreTech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Renovacao De Matricula", {

	onload(frm) {
		escola.utils.auto_fill_academic_year(frm);
	},

	refresh(frm) {
		_set_queries(frm);
		_set_status_indicator(frm);

		// Show invoice link button when submitted and invoice exists
		if (frm.doc.docstatus === 1 && frm.doc.sales_invoice) {
			frm.add_custom_button(__("Ver Factura"), () => {
				frappe.set_route("Form", "Sales Invoice", frm.doc.sales_invoice);
			});
		}
	},

	// When origin year changes, try to auto-fill the target year
	async academic_year(frm) {
		_set_queries(frm);
		if (!frm.doc.academic_year) {
			frm.set_value("target_academic_year", null);
			return;
		}
		const r = await frappe.call({
			method: "escola.escola.doctype.renovacao_de_matricula.renovacao_de_matricula.get_next_academic_year",
			args:   { academic_year: frm.doc.academic_year },
		});
		if (r.message) {
			frm.set_value("target_academic_year", r.message);
		}
	},

	target_academic_year(frm) {
		_set_queries(frm);
	},
});

// ---------------------------------------------------------------------------

function _set_queries(frm) {
	// origin year — any
	frm.set_query("target_academic_year", () => ({
		filters: frm.doc.academic_year
			? { name: ["!=", frm.doc.academic_year] }
			: {},
	}));
}

function _set_status_indicator(frm) {
	if (frm.doc.docstatus === 0) {
		frm.page.set_indicator(__("Rascunho"), "gray");
	} else if (frm.doc.docstatus === 1) {
		frm.page.set_indicator(__("Submetida"), "green");
	} else if (frm.doc.docstatus === 2) {
		frm.page.set_indicator(__("Cancelada"), "red");
	}
}
