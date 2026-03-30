// Copyright (c) 2024, EntreTech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Renovação de Matrícula", {
	onload(frm) {
		escola.utils.auto_fill_academic_year(frm);
	},

	refresh(frm) {
		_set_queries(frm);
		_update_status_indicator(frm);

		if (frm.doc.docstatus === 0 && frm.doc.class_group) {
			frm.add_custom_button(__("Carregar Alunos"), () => _load_students(frm), __("Acções"));
		}

		if (frm.doc.docstatus === 0 && (frm.doc.renovation_students || []).length > 0) {
			frm.add_custom_button(__("Marcar Todos: Sim"), () => _mark_all(frm, "Sim"), __("Acções"));
			frm.add_custom_button(__("Marcar Todos: Não"), () => _mark_all(frm, "Não"), __("Acções"));
		}
	},

	academic_year(frm) {
		frm.set_value("class_group", null);
		_set_queries(frm);
	},

	target_academic_year(frm) {
		frm.set_value("target_class_group", null);
		_set_queries(frm);
	},

	class_group(frm) {
		frm.set_value("renovation_students", []);
		_set_queries(frm);
	},
});

// ---------------------------------------------------------------------------

function _set_queries(frm) {
	// Source class_group filtered by source academic_year
	const srcF = { is_active: 1 };
	if (frm.doc.academic_year) srcF.academic_year = frm.doc.academic_year;
	frm.set_query("class_group", () => ({ filters: srcF }));

	// target_academic_year must differ from source
	if (frm.doc.academic_year) {
		frm.set_query("target_academic_year", () => ({
			filters: { name: ["!=", frm.doc.academic_year] },
		}));
	}

	// target_class_group filtered by target_academic_year
	const tgtF = { is_active: 1 };
	if (frm.doc.target_academic_year) tgtF.academic_year = frm.doc.target_academic_year;
	frm.set_query("target_class_group", () => ({ filters: tgtF }));
	frm.set_query("target_class_group", "renovation_students", () => ({ filters: tgtF }));
}

function _update_status_indicator(frm) {
	const colors = {
		Rascunho:     "gray",
		"Em Processo": "blue",
		Concluída:    "green",
		Cancelada:    "red",
	};
	if (frm.doc.status) {
		frm.page.set_indicator(__(frm.doc.status), colors[frm.doc.status] || "gray");
	}
}

function _load_students(frm) {
	if (!frm.doc.class_group || !frm.doc.academic_year) {
		frappe.msgprint(__("Preencha o Ano Lectivo de Origem e a Turma de Origem primeiro."));
		return;
	}

	frappe.call({
		method: "escola.escola.doctype.renovacao_de_matricula.renovacao_de_matricula.get_students_for_renewal",
		args: {
			class_group: frm.doc.class_group,
			academic_year: frm.doc.academic_year,
		},
		callback(r) {
			if (!r.message || !r.message.length) {
				frappe.msgprint(__("Nenhum aluno activo encontrado nesta turma."));
				return;
			}

			// Clear empty rows before loading
			if ((frm.doc.renovation_students || []).every(row => !row.student)) {
				frm.clear_table("renovation_students");
			}

			r.message.forEach(s => {
				const row = frm.add_child("renovation_students");
				row.student       = s.student;
				row.student_code  = s.student_code;
				row.full_name     = s.full_name;
				row.financial_status = s.financial_status;
				row.renovacao     = s.renovacao || "";
			});

			frm.refresh_field("renovation_students");
			frm.dirty();

			const total = r.message.length;
			const already = r.message.filter(s => s.renovacao).length;
			frappe.show_alert(
				{
					message: already
						? __("{0} aluno(s) carregado(s). {1} já com estado definido.", [total, already])
						: __("{0} aluno(s) carregado(s).", [total]),
					indicator: "green",
				},
				5
			);
		},
	});
}

function _mark_all(frm, value) {
	(frm.doc.renovation_students || []).forEach(row => {
		frappe.model.set_value(row.doctype, row.name, "renovacao", value);
	});
	frm.refresh_field("renovation_students");
}
