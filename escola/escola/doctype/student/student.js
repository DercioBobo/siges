// Copyright (c) 2024, EntreTech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Student", {
	refresh(frm) {
		if (!frm.is_new()) {
			frm.add_custom_button(
				__("Nova Inscrição"),
				() => frappe.new_doc("Inscricao", { student: frm.doc.name })
			);

			frm.add_custom_button(
				__("Registar Transferência"),
				() => frappe.new_doc("Student Transfer", { student: frm.doc.name }),
				__("Acções")
			);

			frm.add_custom_button(
				__("Ver Inscrições"),
				() => frappe.set_route("List", "Inscricao", { student: frm.doc.name }),
				__("Ver")
			);

			frm.add_custom_button(
				__("Ver Transferências"),
				() => frappe.set_route("List", "Student Transfer", { student: frm.doc.name }),
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
