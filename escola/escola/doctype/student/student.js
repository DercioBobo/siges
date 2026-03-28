// Copyright (c) 2024, EntreTech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Student", {
	refresh(frm) {
		if (!frm.is_new()) {
			const status = frm.doc.current_status;

			if (status === "Transferido" || status === "Desistente") {
				frm.add_custom_button(
					__("Reactivar Aluno"),
					() => reactivate_dialog(frm),
					__("Acções")
				);
			}

			frm.add_custom_button(
				__("Registar Transferência"),
				() => frappe.new_doc("Student Transfer", { student: frm.doc.name }),
				__("Acções")
			);

			frm.add_custom_button(
				__("Ver Transferências"),
				() => frappe.set_route("List", "Student Transfer", { student: frm.doc.name }),
				__("Ver")
			);
		}
	},

	first_name(frm) { update_full_name(frm); },
	last_name(frm)  { update_full_name(frm); },
});

function update_full_name(frm) {
	const parts = [frm.doc.first_name, frm.doc.last_name].filter(Boolean);
	frm.set_value("full_name", parts.join(" "));
}

function reactivate_dialog(frm) {
	const d = new frappe.ui.Dialog({
		title: __("Reactivar {0}", [frm.doc.full_name]),
		fields: [
			{
				fieldname: "academic_year",
				fieldtype: "Link",
				options: "Academic Year",
				label: __("Ano Lectivo"),
				reqd: 1,
				onchange() {
					d.set_value("class_group", null);
					d.fields_dict.class_group.get_query = () => ({
						filters: build_filters(d),
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
						filters: build_filters(d),
					});
				},
			},
			{
				fieldname: "class_group",
				fieldtype: "Link",
				options: "Class Group",
				label: __("Turma"),
				reqd: 1,
				get_query: () => ({ filters: build_filters(d) }),
				description: __("Seleccione a turma para o ano lectivo em curso."),
			},
		],
		primary_action_label: __("Reactivar"),
		primary_action(values) {
			frappe.call({
				method: "escola.escola.doctype.inscricao.inscricao.reactivate_student",
				args: {
					student_name: frm.doc.name,
					class_group_name: values.class_group,
				},
				callback(r) {
					if (r.exc) return;
					d.hide();
					frappe.show_alert({
						message: __("Aluno reactivado e atribuído à turma."),
						indicator: "green",
					});
					frm.reload_doc();
				},
			});
		},
	});
	d.show();
}

function build_filters(d) {
	const f = { is_active: 1 };
	const ay = d.get_value("academic_year");
	const sc = d.get_value("school_class");
	if (ay) f.academic_year = ay;
	if (sc) f.school_class = sc;
	return f;
}
