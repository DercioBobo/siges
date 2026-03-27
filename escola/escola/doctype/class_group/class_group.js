// Copyright (c) 2024, EntreTech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Class Group", {
	refresh(frm) {
		frm.set_query("class_teacher", () => ({
			filters: { is_active: 1 },
		}));

		// Roster actions
		frm.add_custom_button(
			__("Reconstruir Pauta"),
			() => rebuild_roster(frm),
			__("Acções")
		);

		// Quick navigation buttons (only for saved, existing records)
		if (!frm.is_new()) {
			frm.add_custom_button(
				__("Pauta de Notas"),
				() => frappe.new_doc("Grade Entry", { class_group: frm.doc.name }),
				__("Criar")
			);

			frm.add_custom_button(
				__("Presença"),
				() => frappe.new_doc("Student Attendance", { class_group: frm.doc.name }),
				__("Criar")
			);

			frm.add_custom_button(
				__("Ver Alocações"),
				() => frappe.set_route("List", "Student Group Assignment", {
					class_group: frm.doc.name,
				}),
				__("Ver")
			);
		}

		// Warn when turma is at capacity
		const count = frm.doc.student_count || 0;
		const max = frm.doc.max_students || 0;
		if (max > 0 && count >= max) {
			frm.dashboard.set_headline_alert(
				__("Turma com capacidade esgotada ({0}/{1} alunos)", [count, max]),
				"red"
			);
		} else if (max > 0) {
			frm.dashboard.set_headline_alert(
				__("{0}/{1} alunos", [count, max]),
				count / max >= 0.9 ? "orange" : "green"
			);
		}
	},
});

function rebuild_roster(frm) {
	frappe.confirm(
		__("Isto irá reconstruir a lista de alunos a partir das Alocações de Turma activas. Continuar?"),
		() => {
			frappe.call({
				method: "escola.escola.doctype.class_group.class_group.rebuild_roster",
				args: { class_group_name: frm.doc.name },
				freeze: true,
				freeze_message: __("A reconstruir a pauta…"),
				callback(r) {
					if (r.message !== undefined) {
						frappe.show_alert({
							message: __("Pauta reconstruída com {0} aluno(s).", [r.message]),
							indicator: "green",
						});
						frm.reload_doc();
					}
				},
			});
		}
	);
}
