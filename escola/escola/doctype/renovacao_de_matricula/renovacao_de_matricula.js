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
		_load_fee_info(frm, "renewal_fee_amount", __("Valor da Taxa de Renovação"));

		if (frm.doc.docstatus === 1 && frm.doc.sales_invoice) {
			frm.add_custom_button(__("Ver Factura"), () => {
				frappe.set_route("Form", "Sales Invoice", frm.doc.sales_invoice);
			});
		}

		if (frm.doc.docstatus === 1) {
			_check_reactivation(frm);
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
// Child table events
// ---------------------------------------------------------------------------

frappe.ui.form.on("Renovacao Payment", {
	async mode_of_payment(frm, cdt, cdn) {
		if (frm.doc.docstatus !== 0) return;
		const fee = await frappe.db.get_single_value("School Settings", "renewal_fee_amount");
		frappe.model.set_value(cdt, cdn, "amount", parseFloat(fee) || 0);
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
	const grid = frm.get_field("payments").grid;
	grid.toggle_enable(editable);
	grid.toggle_add_delete_rows(editable);
	grid.editable_grid = true;

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

	const fee = parseFloat(await frappe.db.get_single_value("School Settings", "renewal_fee_amount")) || 0;
	const count = doc.payments.length;

	(doc.payments || []).forEach((p, i) => {
		const row = frm.add_child("payments");
		row.mode_of_payment = p.mode_of_payment;
		// Distribute fee evenly across payment methods; last row gets remainder
		row.amount = count === 1 ? fee : (i < count - 1 ? Math.floor(fee / count * 100) / 100 : 0);
	});
	frm.refresh_field("payments");
}

async function _load_fee_info(frm, settings_field, label) {
	const wrapper = frm.fields_dict.fee_info_html?.$wrapper;
	if (!wrapper) return;
	const amount = await frappe.db.get_single_value("School Settings", settings_field);
	if (amount && parseFloat(amount) > 0) {
		const fmt = frappe.format(parseFloat(amount), { fieldtype: "Currency" });
		wrapper.html(
			`<p style="color:var(--text-muted);font-size:13px;margin:0 0 8px;">
				${label}: <strong style="color:var(--text-color);">${fmt}</strong>
			</p>`
		);
	} else {
		wrapper.html("");
	}
}

// ---------------------------------------------------------------------------
// Renewal hold reactivation
// ---------------------------------------------------------------------------

async function _check_reactivation(frm) {
	const r = await frappe.call({
		method: "escola.escola.renewal_hold.get_reactivation_options",
		args:   { doc_name: frm.doc.name },
	});
	if (r.message) {
		_show_reactivation_dialog(frm, r.message);
	}
}

function _show_reactivation_dialog(frm, opts) {
	const groups = opts.available_groups || [];

	if (!groups.length) {
		frappe.msgprint({
			title: __("Sem Vagas Disponíveis"),
			message: __("O aluno <b>{0}</b> está Pendente de Renovação mas não há turmas com vagas disponíveis para {1}.", [opts.student_name, opts.target_year]),
			indicator: "orange",
		});
		return;
	}

	// Build Select options: original first, then others
	const select_options = groups.map(g => {
		const tag   = g.is_original ? ` (${__("turma original")})` : "";
		const seats = g.max_students ? ` — ${g.current_count}/${g.max_students}` : "";
		return { value: g.name, label: `${g.name}${tag}${seats}` };
	});

	const dialog = new frappe.ui.Dialog({
		title: __("Reactivar Aluno — {0}", [opts.student_name]),
		fields: [
			{
				fieldtype: "HTML",
				options: `<p style="margin:0 0 12px;color:var(--text-muted);">
					${__("O aluno está em estado <b>Pendente de Renovação</b>. Seleccione a turma para reactivar.")}
				</p>`,
			},
			{
				fieldname:  "class_group",
				fieldtype:  "Select",
				label:      __("Turma"),
				options:    select_options.map(o => o.value).join("\n"),
				default:    select_options[0].value,
				reqd:       1,
				description: select_options.map(o => `${o.value}: ${o.label}`).join(" | "),
			},
		],
		primary_action_label: __("Reactivar"),
		async primary_action(values) {
			dialog.hide();
			frappe.show_progress(__("A reactivar..."), 0, 100);
			try {
				const res = await frappe.call({
					method: "escola.escola.renewal_hold.reactivate_student",
					args: {
						student:       opts.student,
						class_group:   values.class_group,
						academic_year: opts.target_year,
					},
				});
				frappe.hide_progress();
				if (res.message) {
					frappe.show_alert({
						message: __("Aluno reactivado e alocado à turma <b>{0}</b>.", [res.message.class_group]),
						indicator: "green",
					}, 5);
					frm.reload_doc();
				}
			} catch (e) {
				frappe.hide_progress();
			}
		},
	});

	// Replace select element with a proper label/description per option
	dialog.show();

	// Rebuild the select with human-readable labels
	const sf = dialog.fields_dict.class_group;
	if (sf && sf.$input) {
		sf.$input.empty();
		select_options.forEach(o => {
			sf.$input.append(`<option value="${o.value}">${o.label}</option>`);
		});
		sf.$input.val(select_options[0].value);
	}
}
