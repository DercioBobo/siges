// Copyright (c) 2024, EntreTech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Renovacao De Matricula", {

	onload(frm) {
		escola.utils.auto_fill_academic_year(frm);
	},

	refresh(frm) {
		_set_queries(frm);
		_set_status_indicator(frm);
		_toggle_payments_grid(frm);

		if (frm.doc.docstatus === 1 && frm.doc.sales_invoice) {
			frm.add_custom_button(__("Ver Factura"), () => {
				frappe.set_route("Form", "Sales Invoice", frm.doc.sales_invoice);
			});
		}
	},

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

function _toggle_payments_grid(frm) {
	const editable = frm.doc.docstatus === 0;
	frm.get_field("payments").grid.toggle_enable(editable);
	frm.get_field("payments").grid.toggle_add_delete_rows(editable);

	// Pre-load payment methods from School Settings POS profile on new docs
	if (frm.doc.__islocal && !(frm.doc.payments && frm.doc.payments.length)) {
		_prefill_payments_from_pos(frm);
	}
}

async function _prefill_payments_from_pos(frm) {
	const pos_profile = await frappe.db.get_single_value("School Settings", "renewal_pos_profile");
	if (!pos_profile) return;

	const doc = await frappe.db.get_doc("POS Profile", pos_profile);
	if (!doc || !doc.payments || !doc.payments.length) return;

	(doc.payments || []).forEach(p => {
		const row = frm.add_child("payments");
		row.mode_of_payment = p.mode_of_payment;
		row.amount = 0;
	});
	frm.refresh_field("payments");
}
