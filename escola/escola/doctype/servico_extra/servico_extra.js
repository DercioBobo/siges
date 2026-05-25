// Copyright (c) 2024, EntreTech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Servico Extra", {
	refresh(frm) {
		if (!frm.doc.__islocal) {
			frm.add_custom_button(__("Actualizar Preço"), () => _update_price_dialog(frm));
		}
	},
});

function _update_price_dialog(frm) {
	frappe.prompt(
		[
			{
				fieldname: "new_amount",
				fieldtype: "Currency",
				label: __("Novo Valor (MZN)"),
				reqd: 1,
				default: frm.doc.current_amount,
				description: __("Valor actual: {0} MZN", [frappe.format(frm.doc.current_amount, { fieldtype: "Currency" })]),
			},
			{
				fieldname: "motive",
				fieldtype: "Data",
				label: __("Motivo"),
				reqd: 1,
				description: __("Ex.: Aumento de combustível, novo contrato, revisão anual."),
			},
		],
		(values) => {
			frappe.call({
				method: "escola.escola.doctype.servico_extra.servico_extra.update_price",
				args: {
					doc_name: frm.docname,
					new_amount: values.new_amount,
					motive: values.motive,
				},
				callback(r) {
					if (!r.exc) {
						frappe.show_alert({
							message: __("Preço actualizado. Efectivo no próximo ciclo de facturação."),
							indicator: "green",
						}, 5);
						frm.reload_doc();
					}
				},
			});
		},
		__("Actualizar Preço"),
		__("Confirmar")
	);
}
