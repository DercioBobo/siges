// Copyright (c) 2024, EntreTech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Grade Entry", {
	refresh(frm) {
		set_queries(frm);

		frm.add_custom_button(__("Carregar Alunos e Disciplinas"), () => {
			load_grade_rows(frm);
		});
	},

	academic_year(frm) {
		frm.set_value("academic_term", null);
		frm.set_value("class_group", null);
		set_queries(frm);
	},

	school_class(frm) {
		frm.set_value("class_group", null);
		set_queries(frm);
	},

	class_group(frm) {
		set_queries(frm);
	},
});

function set_queries(frm) {
	frm.set_query("academic_term", () => {
		const filters = { is_active: 1 };
		if (frm.doc.academic_year) filters.academic_year = frm.doc.academic_year;
		return { filters };
	});

	const cg_filters = { is_active: 1 };
	if (frm.doc.academic_year) cg_filters.academic_year = frm.doc.academic_year;
	if (frm.doc.school_class) cg_filters.school_class = frm.doc.school_class;
	frm.set_query("class_group", () => ({ filters: cg_filters }));

	frm.set_query("school_class", () => ({ filters: { is_active: 1 } }));
}

async function load_grade_rows(frm) {
	if (!frm.doc.class_group || !frm.doc.academic_year) {
		frappe.msgprint(
			__("Por favor, seleccione a Turma e o Ano Lectivo antes de carregar as linhas.")
		);
		return;
	}

	const r = await frappe.call({
		method:
			"escola.escola.doctype.grade_entry.grade_entry.get_students_and_subjects",
		args: {
			class_group: frm.doc.class_group,
			academic_year: frm.doc.academic_year,
		},
	});

	if (!r.message) return;

	// Handle structured error responses
	if (r.message.error === "no_students") {
		frappe.msgprint(
			__("Não foram encontrados alunos activos para a turma <b>{0}</b> no ano lectivo seleccionado. "
				+ "Verifique as Alocações de Turma.", [frm.doc.class_group])
		);
		return;
	}
	if (r.message.error === "no_subjects") {
		frappe.msgprint(
			__("Não existem disciplinas atribuídas à turma <b>{0}</b>. "
				+ "Crie as Atribuições de Disciplina primeiro.", [frm.doc.class_group])
		);
		return;
	}

	// Build set of existing student+subject pairs to avoid duplicates
	const existing = new Set(
		(frm.doc.grade_rows || []).map((r) => r.student + "||" + r.subject)
	);

	let added = 0;
	for (const combo of r.message) {
		const key = combo.student + "||" + combo.subject;
		if (!existing.has(key)) {
			const row = frappe.model.add_child(
				frm.doc,
				"Grade Entry Row",
				"grade_rows"
			);
			row.student = combo.student;
			row.subject = combo.subject;
			if (combo.teacher) row.teacher = combo.teacher;
			added++;
		}
	}

	frm.refresh_field("grade_rows");

	if (added > 0) {
		frappe.show_alert({
			message: __("{0} linha(s) adicionada(s) à pauta.", [added]),
			indicator: "green",
		});
	} else {
		frappe.show_alert({
			message: __(
				"Todas as combinações de aluno/disciplina já constam da pauta."
			),
			indicator: "blue",
		});
	}
}
