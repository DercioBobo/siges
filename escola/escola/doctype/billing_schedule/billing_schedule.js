// Copyright (c) 2024, EntreTech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Billing Schedule", {
	onload(frm) {
		frm.set_query("school_class", () => ({ filters: { is_active: 1 } }));

		// Pre-fill invoice_day and due_days from School Settings on new docs
		if (frm.is_new()) {
			frappe.db.get_value(
				"School Settings", "School Settings",
				["invoice_posting_day", "invoice_due_days"],
				r => {
					if (r) {
						if (!frm.doc.invoice_day && r.invoice_posting_day)
							frm.set_value("invoice_day", r.invoice_posting_day);
						if (!frm.doc.due_days && r.invoice_due_days)
							frm.set_value("due_days", r.invoice_due_days);
					}
				}
			);
		}
	},

	refresh(frm) {
		if (!frm.is_new()) {
			frm.add_custom_button(__("Executar Agora"), () => {
				frappe.confirm(
					__("Gerar facturas para este agendamento imediatamente?"),
					() => {
						frappe.call({
							method: "escola.escola.doctype.billing_schedule.billing_schedule.run_now",
							args:   { schedule_name: frm.doc.name },
							freeze: true,
							freeze_message: __("A gerar facturas…"),
							callback(r) {
								if (r.exc) return;
								const m = r.message || {};
								if (m.skipped) {
									frappe.msgprint(__("Já existe um ciclo para este período — nada foi criado."));
								} else {
									frappe.msgprint(__("{0} factura(s) criada(s), {1} ignorada(s).",
										[m.created || 0, m.skipped || 0]));
								}
								frm.reload_doc();
							},
						});
					}
				);
			});

			_load_info(frm);
		}
	},

	school_class(frm) {
		_suggest_name(frm);
	},

	billing_mode(frm) {
		_suggest_name(frm);
		frm.toggle_reqd("billing_month", ["Trimestral", "Anual"].includes(frm.doc.billing_mode));
	},
});

function _suggest_name(frm) {
	if (!frm.is_new() || frm.doc.schedule_name) return;
	if (!frm.doc.school_class || !frm.doc.billing_mode) return;
	frm.set_value("schedule_name", `${frm.doc.school_class} · ${frm.doc.billing_mode}`);
}

function _load_info(frm) {
	frappe.call({
		method: "escola.escola.doctype.billing_schedule.billing_schedule.get_schedule_info",
		args:   { schedule_name: frm.doc.name },
		callback(r) {
			if (!r.message) return;
			const { next_due_date, student_count, expected_total } = r.message;
			const fmt_date = next_due_date
				? frappe.datetime.str_to_user(next_due_date)
				: __("N/D");
			frm.dashboard.set_headline_alert(
				__("Próxima emissão: <b>{0}</b> · {1} alunos · {2} esperado",
					[fmt_date, student_count || 0, format_currency(expected_total || 0)]),
				"blue"
			);
		},
	});
}
