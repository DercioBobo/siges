// Copyright (c) 2024, EntreTech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Class Group", {
	refresh(frm) {
		frm.set_query("class_teacher", () => ({
			filters: { is_active: 1 },
		}));

		if (!frm.is_new()) {
			// Primary student management buttons (standalone, prominent)
			frm.add_custom_button(__("Adicionar Aluno(s)"), () => add_students_dialog(frm));

			const has_students = (frm.doc.students || []).length > 0;
			if (has_students) {
				frm.add_custom_button(
					__("Remover Aluno"),
					() => remove_student_dialog(frm)
				);
			}

			// Secondary navigation
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

			frm.add_custom_button(
				__("Reconstruir Pauta"),
				() => rebuild_roster(frm),
				__("Acções")
			);
		}

		// Capacity indicator
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

// ---------------------------------------------------------------------------
// Student management dialogs
// ---------------------------------------------------------------------------

function add_students_dialog(frm) {
	const d = new frappe.ui.Dialog({
		title: __("Adicionar Aluno(s) à Turma {0}", [frm.doc.group_name]),
		fields: [
			{
				fieldname: "students",
				fieldtype: "Table",
				label: __("Alunos a adicionar"),
				fields: [
					{
						fieldname: "student",
						fieldtype: "Link",
						options: "Student",
						label: __("Aluno"),
						in_list_view: 1,
						reqd: 1,
						columns: 4,
						get_query: () => ({ filters: { is_active: 1 } }),
					},
					{
						fieldname: "student_name",
						fieldtype: "Data",
						label: __("Nome"),
						in_list_view: 1,
						read_only: 1,
						columns: 6,
					},
				],
			},
		],
		primary_action_label: __("Atribuir"),
		primary_action(values) {
			const students = (values.students || [])
				.map((r) => r.student)
				.filter(Boolean);

			if (!students.length) {
				frappe.msgprint(__("Adicione pelo menos um aluno à lista."));
				return;
			}

			frappe.call({
				method: "escola.escola.doctype.class_group.class_group.add_students_to_group",
				args: {
					class_group_name: frm.doc.name,
					students: JSON.stringify(students),
				},
				freeze: true,
				freeze_message: __("A atribuir alunos..."),
				callback(r) {
					if (r.exc) return;
					d.hide();
					const { created, skipped, errors } = r.message;

					if (errors && errors.length) {
						const items = errors
							.map((e) => `<li><b>${e.student}</b>: ${e.error}</li>`)
							.join("");
						frappe.msgprint({
							title: __("Alguns alunos não foram atribuídos"),
							message: `<ul>${items}</ul>`,
							indicator: "orange",
						});
					}

					const parts = [];
					if (created > 0)
						parts.push(__("{0} aluno(s) atribuído(s)", [created]));
					if (skipped > 0)
						parts.push(__("{0} já estava(m) na turma", [skipped]));
					if (parts.length) {
						frappe.show_alert({
							message: parts.join(" · "),
							indicator: created > 0 ? "green" : "blue",
						});
					}

					frm.reload_doc();
				},
			});
		},
	});

	// Pre-wire student → student_name lookup
	d.fields_dict.students.grid.wrapper.on(
		"change",
		"[data-fieldname='student'] input",
		function () {
			const grid_row = $(this).closest(".grid-row");
			const row_idx = grid_row.attr("data-idx") - 1;
			const row = d.fields_dict.students.grid.grid_rows[row_idx];
			if (!row) return;
			const student_val = row.get_field("student").get_value();
			if (!student_val) {
				row.get_field("student_name").set_value("");
				return;
			}
			frappe.db.get_value("Student", student_val, "student_name", (r) => {
				if (r && r.student_name) {
					row.get_field("student_name").set_value(r.student_name);
				}
			});
		}
	);

	d.show();
}

function remove_student_dialog(frm) {
	const roster = frm.doc.students || [];
	if (!roster.length) {
		frappe.msgprint(__("Não há alunos nesta turma."));
		return;
	}

	const d = new frappe.ui.Dialog({
		title: __("Remover Aluno da Turma"),
		fields: [
			{
				fieldname: "student",
				fieldtype: "Link",
				options: "Student",
				label: __("Aluno"),
				reqd: 1,
				description: __("Apenas alunos actualmente nesta turma são apresentados."),
				get_query: () => ({
					filters: {
						name: ["in", roster.map((r) => r.student)],
					},
				}),
			},
		],
		primary_action_label: __("Remover da Turma"),
		primary_action(values) {
			frappe.confirm(
				__("Confirma a remoção de <b>{0}</b> desta turma? O registo de alocação ficará marcado como Encerrado.", [values.student]),
				() => {
					frappe.call({
						method: "escola.escola.doctype.class_group.class_group.remove_student_from_group",
						args: {
							class_group_name: frm.doc.name,
							student: values.student,
						},
						callback(r) {
							if (r.exc) return;
							d.hide();
							frappe.show_alert({
								message: __("Aluno removido da turma."),
								indicator: "green",
							});
							frm.reload_doc();
						},
					});
				}
			);
		},
	});

	d.show();
}

// ---------------------------------------------------------------------------
// Rebuild roster
// ---------------------------------------------------------------------------

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
