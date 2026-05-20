// Copyright (c) 2024, EntreTech and contributors
// For license information, please see license.txt

const _MIN_DISCOUNT_PERIODS = 6;
const _DISCOUNT_SIX_PLUS    = 5;
const _DISCOUNT_FULL_YEAR   = 10;

frappe.ui.form.on("Adiantamento De Pagamento", {
	setup(frm) {
		frm.set_query("student", () => ({ filters: { current_status: "Activo" } }));
		frm.set_query("pos_profile", () => ({}));
	},

	refresh(frm) {
		_update_discount_badge(frm);

		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(__("Carregar Períodos Disponíveis"), () => _load_periods(frm), __("Ferramentas"));
		}

		if (frm.doc.docstatus === 1 && frm.doc.sales_invoice) {
			frm.add_custom_button(__("Ver Factura"), () => {
				frappe.set_route("Form", "Sales Invoice", frm.doc.sales_invoice);
			});
		}
	},

	student(frm) {
		if (!frm.doc.student) {
			frm.set_value("student_full_name", "");
			frm.set_value("school_class", "");
			frm.clear_table("periods");
			frm.refresh_field("periods");
			return;
		}
		frappe.db.get_value("Student", frm.doc.student, ["full_name", "current_school_class", "current_class_group"])
			.then(r => {
				if (!r.message) return;
				frm.set_value("student_full_name", r.message.full_name || "");
				frm.set_value("school_class",      r.message.current_school_class || "");

				// Auto-fill academic_year from current class group if not already set
				if (!frm.doc.academic_year && r.message.current_class_group) {
					frappe.db.get_value("Class Group", r.message.current_class_group, "academic_year")
						.then(cg => {
							if (cg.message && cg.message.academic_year) {
								frm.set_value("academic_year", cg.message.academic_year);
							}
						});
				}

				// Clear periods when student changes
				frm.clear_table("periods");
				frm.refresh_field("periods");
				_recalculate(frm);
			});
	},

	academic_year(frm) {
		frm.clear_table("periods");
		frm.refresh_field("periods");
		_recalculate(frm);
	},

	is_pos(frm) {
		if (!frm.doc.is_pos) {
			frm.clear_table("payments");
			frm.refresh_field("payments");
		}
	},
});

// Recalculate when period rows change
frappe.ui.form.on("Adiantamento Period Line", {
	periods_remove(frm) { _recalculate(frm); },
	gross_amount(frm)   { _recalculate(frm); },
});

// ---------------------------------------------------------------------------
// Load available periods from server
// ---------------------------------------------------------------------------

async function _load_periods(frm) {
	if (!frm.doc.student) {
		frappe.msgprint(__("Seleccione o aluno primeiro."));
		return;
	}
	if (!frm.doc.academic_year) {
		frappe.msgprint(__("Seleccione o Ano Lectivo primeiro."));
		return;
	}

	frappe.show_progress(__("A carregar períodos…"), 0, 100);

	const r = await frappe.call({
		method: "escola.escola.doctype.adiantamento_de_pagamento.adiantamento_de_pagamento.get_available_periods",
		args:   { student: frm.doc.student, academic_year: frm.doc.academic_year },
	});

	frappe.hide_progress();

	if (r.exc || !r.message) return;

	const periods = r.message;
	if (!periods.length) {
		frappe.msgprint({
			title:     __("Sem períodos disponíveis"),
			message:   __("Todos os períodos do ano lectivo já estão cobertos por facturas ou adiantamentos, ou não existe nenhum agendamento activo para esta classe."),
			indicator: "orange",
		});
		return;
	}

	// Only add periods not already in the table
	const existing = new Set(
		(frm.doc.periods || []).map(p => p.posting_date)
	);

	let added = 0;
	periods.forEach(p => {
		if (!existing.has(p.posting_date)) {
			const row = frm.add_child("periods");
			row.period_label = p.period_label;
			row.posting_date = p.posting_date;
			row.billing_mode = p.billing_mode;
			row.gross_amount = p.gross_amount;
			added++;
		}
	});

	frm.refresh_field("periods");
	_recalculate(frm);

	frappe.show_alert({
		message:   __("{0} período(s) carregado(s).", [added]),
		indicator: "green",
	}, 4);
}

// ---------------------------------------------------------------------------
// Recalculate summary
// ---------------------------------------------------------------------------

function _recalculate(frm) {
	const periods   = frm.doc.periods || [];
	const n         = periods.length;
	const gross     = periods.reduce((s, p) => s + (parseFloat(p.gross_amount) || 0), 0);
	const full_year = parseInt(frm.doc.full_year_periods) || 0;

	let pct    = 0;
	let reason = "";
	if (n > 0 && full_year > 0 && n === full_year) {
		pct    = _DISCOUNT_FULL_YEAR;
		reason = __("Ano Lectivo completo ({0}%)", [pct]);
	} else if (n >= _MIN_DISCOUNT_PERIODS) {
		pct    = _DISCOUNT_SIX_PLUS;
		reason = __("{0} períodos ou mais ({1}%)", [_MIN_DISCOUNT_PERIODS, pct]);
	}

	const discount = gross * pct / 100;
	const net      = gross - discount;

	frm.set_value("total_periods",   n);
	frm.set_value("gross_total",     gross);
	frm.set_value("discount_percent", pct);
	frm.set_value("discount_reason", reason);
	frm.set_value("discount_total",  discount);
	frm.set_value("net_total",       net);

	_update_discount_badge(frm);
	_sync_payments_total(frm, net);
}

// ---------------------------------------------------------------------------
// UI helpers
// ---------------------------------------------------------------------------

function _update_discount_badge(frm) {
	const pct = parseFloat(frm.doc.discount_percent) || 0;
	if (pct > 0) {
		frm.dashboard.set_headline(
			`<span style="color:#059669;font-weight:600;">🏷 ${__("Desconto de {0}% aplicado", [pct])} — ${frappe.utils.escape_html(frm.doc.discount_reason || "")}</span>`
		);
	} else {
		frm.dashboard.set_headline("");
	}
}

function _sync_payments_total(frm, net_total) {
	if (!frm.doc.is_pos) return;
	const payments = frm.doc.payments || [];
	if (payments.length !== 1) return;
	// If there's exactly one payment row, auto-update its amount to match net_total
	frappe.model.set_value(payments[0].doctype, payments[0].name, "amount", net_total);
	frm.refresh_field("payments");
}
