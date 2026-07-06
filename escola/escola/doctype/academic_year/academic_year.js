// Copyright (c) 2024, EntreTech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Academic Year", {
	refresh(frm) {
		if (!frm.is_new() && frm.doc.is_active) {
			frm.dashboard.set_headline_alert(
				__("Este é o Ano Lectivo actual."),
				"green"
			);
		}

		if (!frm.is_new()) {
			frappe.db
				.count("Academic Term", { filters: { academic_year: frm.doc.name } })
				.then((n) => {
					if (!n) {
						frm.add_custom_button(__("Criar Trimestres"), () =>
							open_terms_dialog(frm)
						);
					}
				});
		}
	},
});

function open_terms_dialog(frm) {
	// Default dates: split the year's range into three equal segments.
	const total = frappe.datetime.get_diff(frm.doc.end_date, frm.doc.start_date);
	const seg = Math.floor(total / 3);
	const add = (n) => frappe.datetime.add_days(frm.doc.start_date, n);

	const defaults = [
		["1º", frm.doc.start_date, add(seg - 1)],
		["2º", add(seg), add(2 * seg - 1)],
		["3º", add(2 * seg), frm.doc.end_date],
	];

	const fields = [];
	defaults.forEach(([prefix, start, end], i) => {
		fields.push(
			{ fieldtype: "Section Break", label: __("{0} Trimestre", [prefix]) },
			{
				fieldname: `name_${i}`,
				fieldtype: "Data",
				label: __("Nome"),
				default: `${prefix} Trimestre ${frm.doc.year_name}`,
				reqd: 1,
			},
			{ fieldtype: "Column Break" },
			{
				fieldname: `start_${i}`,
				fieldtype: "Date",
				label: __("Data de Início"),
				default: start,
				reqd: 1,
			},
			{ fieldtype: "Column Break" },
			{
				fieldname: `end_${i}`,
				fieldtype: "Date",
				label: __("Data de Fim"),
				default: end,
				reqd: 1,
			}
		);
	});

	const dlg = new frappe.ui.Dialog({
		title: __("Criar Trimestres — {0}", [frm.doc.year_name]),
		size: "large",
		fields,
		primary_action_label: __("Criar Períodos"),
		primary_action(values) {
			const terms = [0, 1, 2].map((i) => ({
				term_name: values[`name_${i}`],
				start_date: values[`start_${i}`],
				end_date: values[`end_${i}`],
			}));
			frappe.call({
				method: "escola.escola.doctype.academic_year.academic_year.create_terms",
				args: { academic_year: frm.doc.name, terms },
				freeze: true,
				freeze_message: __("A criar períodos…"),
				callback(r) {
					dlg.hide();
					const res = r.message || {};
					const created = (res.created || []).length;
					const skipped = res.skipped || [];
					if (created) {
						frappe.show_alert({
							message: __("{0} período(s) criado(s) com sucesso.", [created]),
							indicator: "green",
						});
					}
					if (skipped.length) {
						frappe.msgprint(
							__("Já existiam e foram ignorados: {0}", [skipped.join(", ")])
						);
					}
					frm.refresh();
				},
			});
		},
	});
	dlg.show();
}
