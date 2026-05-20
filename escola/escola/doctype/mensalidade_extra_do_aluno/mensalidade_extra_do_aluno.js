// Copyright (c) 2024, EntreTech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Mensalidade Extra do Aluno", {
	refresh(frm) {
		_toggle_services_grid(frm);
		if (!frm.doc.__islocal && frm.doc.docstatus === 0) {
			const hasActive = (frm.doc.services || []).some(r => r.status === "Activo");
			if (hasActive) {
				frm.add_custom_button(__("Cancelar Serviço"), () => _cancel_service_dialog(frm));
			}
		}
	},
});

function _toggle_services_grid(frm) {
	const grid = frm.fields_dict.services && frm.fields_dict.services.grid;
	if (!grid) return;
	grid.editable_grid = true;
	grid.toggle_enable(frm.doc.docstatus === 0);
}

async function _cancel_service_dialog(frm) {
	const r = await frappe.call({
		method: "escola.escola.doctype.mensalidade_extra_do_aluno.mensalidade_extra_do_aluno.get_active_services_for_student",
		args: { student: frm.doc.student },
	});

	const active = r.message || [];
	if (!active.length) {
		frappe.msgprint(__("Não há serviços activos para cancelar."));
		return;
	}

	const fields = active.map(s => ({
		fieldname: "svc_" + s.row_name.replace(/-/g, "_"),
		fieldtype: "Check",
		label: `${frappe.utils.escape_html(s.service_name)} — ${frappe.format(s.current_amount, { fieldtype: "Currency" })} MZN`,
		default: 0,
	}));

	fields.push({
		fieldname: "motive",
		fieldtype: "Data",
		label: __("Motivo"),
		reqd: 1,
		description: __("Ex.: Desistência do serviço, mudança de turno."),
	});

	const d = new frappe.ui.Dialog({
		title: __("Cancelar Serviço — {0}", [frm.doc.student_full_name]),
		fields,
		primary_action_label: __("Confirmar Cancelamento"),
		primary_action(values) {
			const selected = active
				.filter(s => values["svc_" + s.row_name.replace(/-/g, "_")])
				.map(s => s.row_name);

			if (!selected.length) {
				frappe.msgprint(__("Seleccione pelo menos um serviço para cancelar."));
				return;
			}
			d.hide();

			frappe.call({
				method: "escola.escola.doctype.mensalidade_extra_do_aluno.mensalidade_extra_do_aluno.cancel_services",
				args: {
					doc_name: frm.docname,
					services: JSON.stringify(selected),
					motive: values.motive,
				},
				freeze: true,
				freeze_message: __("A cancelar serviços…"),
				callback(r) {
					if (!r.exc) {
						frappe.show_alert({
							message: __("{0} serviço(s) cancelado(s). Efectivo no próximo ciclo de facturação.", [r.message.cancelled]),
							indicator: "orange",
						}, 5);
						frm.reload_doc();
					}
				},
			});
		},
	});
	d.show();
}
