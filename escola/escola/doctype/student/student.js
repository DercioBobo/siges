// Copyright (c) 2024, EntreTech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Student", {
	refresh(frm) {
		if (!frm.is_new()) {
			frm.add_custom_button(__("Atribuir a Turma"), () => assign_to_class_dialog(frm));

			frm.add_custom_button(
				__("Ver Alocações"),
				() => frappe.set_route("List", "Student Group Assignment", { student: frm.doc.name }),
				__("Ver")
			);
		}
	},

	first_name(frm) {
		update_full_name(frm);
	},
	last_name(frm) {
		update_full_name(frm);
	},
});

function update_full_name(frm) {
	const parts = [frm.doc.first_name, frm.doc.last_name].filter(Boolean);
	frm.set_value("full_name", parts.join(" "));
}

function assign_to_class_dialog(frm) {
	const d = new frappe.ui.Dialog({
		title: __("Atribuir {0} a uma Turma", [frm.doc.full_name || frm.doc.name]),
		fields: [
			{
				fieldname: "academic_year",
				fieldtype: "Link",
				options: "Academic Year",
				label: __("Ano Lectivo"),
				reqd: 1,
				onchange() {
					// Refresh class_group query when year changes
					d.set_value("school_class", null);
					d.set_value("class_group", null);
					d.fields_dict.class_group.get_query = () => ({
						filters: build_cg_filters(d),
					});
				},
			},
			{
				fieldname: "school_class",
				fieldtype: "Link",
				options: "School Class",
				label: __("Classe"),
				get_query: () => ({ filters: { is_active: 1 } }),
				onchange() {
					d.set_value("class_group", null);
					d.fields_dict.class_group.get_query = () => ({
						filters: build_cg_filters(d),
					});
				},
			},
			{
				fieldname: "class_group",
				fieldtype: "Link",
				options: "Class Group",
				label: __("Turma"),
				reqd: 1,
				get_query: () => ({ filters: build_cg_filters(d) }),
				description: __("Seleccione o Ano Lectivo primeiro para filtrar as turmas disponíveis."),
			},
		],
		primary_action_label: __("Atribuir"),
		primary_action(values) {
			frappe.call({
				method: "escola.escola.doctype.class_group.class_group.add_students_to_group",
				args: {
					class_group_name: values.class_group,
					students: JSON.stringify([frm.doc.name]),
				},
				callback(r) {
					if (r.exc) return;
					d.hide();
					const { created, skipped, errors } = r.message;

					if (errors && errors.length) {
						frappe.msgprint({
							title: __("Erro na atribuição"),
							message: errors[0].error,
							indicator: "red",
						});
						return;
					}

					if (skipped > 0) {
						frappe.msgprint(__("Este aluno já está atribuído a esta turma."));
					} else {
						frappe.show_alert({
							message: __("Aluno atribuído com sucesso."),
							indicator: "green",
						});
					}
				},
			});
		},
	});

	d.show();
}

function build_cg_filters(d) {
	const filters = { is_active: 1 };
	const ay = d.get_value("academic_year");
	const sc = d.get_value("school_class");
	if (ay) filters.academic_year = ay;
	if (sc) filters.school_class = sc;
	return filters;
}
