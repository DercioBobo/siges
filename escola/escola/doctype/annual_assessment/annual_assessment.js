// Copyright (c) 2024, EntreTech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Annual Assessment", {
	refresh(frm) {
		set_queries(frm);

		frm.add_custom_button(__("Calcular Avaliação"), () => {
			maybe_calculate(frm);
		});
	},

	academic_year(frm) {
		frm.set_value("class_group", null);
		set_queries(frm);
	},

	school_class(frm) {
		frm.set_value("class_group", null);
		set_queries(frm);
	},
});

function set_queries(frm) {
	const cg_filters = { is_active: 1 };
	if (frm.doc.academic_year) cg_filters.academic_year = frm.doc.academic_year;
	if (frm.doc.school_class) cg_filters.school_class = frm.doc.school_class;

	frm.set_query("class_group", () => ({ filters: cg_filters }));
	frm.set_query("assessment_scheme", () => ({ filters: { is_active: 1 } }));
}

function maybe_calculate(frm) {
	if (!frm.doc.academic_year || !frm.doc.class_group || !frm.doc.assessment_scheme) {
		frappe.msgprint(
			__("Por favor, seleccione o Ano Lectivo, a Turma e o Modelo de Avaliação antes de calcular.")
		);
		return;
	}

	if (frm.is_dirty() || frm.is_new()) {
		frappe.msgprint(__("Por favor, guarde o documento antes de calcular."));
		return;
	}

	const has_rows = frm.doc.assessment_rows && frm.doc.assessment_rows.length > 0;

	if (has_rows) {
		frappe.confirm(
			__("Já existem resultados calculados. Recalcular irá substituir todos os valores actuais. Continuar?"),
			() => do_calculate(frm)
		);
	} else {
		do_calculate(frm);
	}
}

async function do_calculate(frm) {
	const r = await frappe.call({
		method:
			"escola.escola.doctype.annual_assessment.annual_assessment.calculate_assessment",
		args: { doc_name: frm.doc.name },
		freeze: true,
		freeze_message: __("A calcular avaliação…"),
	});

	if (!r.message) return;

	if (r.message.error === "no_grade_entries") {
		frappe.msgprint(
			__("Não foram encontradas Pautas de Notas para a Turma <b>{0}</b> "
				+ "no Ano Lectivo <b>{1}</b>. Introduza as notas nas Pautas primeiro.",
				[frm.doc.class_group, frm.doc.academic_year])
		);
		return;
	}
	if (r.message.error === "no_grades") {
		frappe.msgprint(
			__("As Pautas de Notas desta turma não têm valores preenchidos. "
				+ "Introduza as notas antes de calcular a avaliação anual.")
		);
		return;
	}

	// Replace table contents
	frm.doc.assessment_rows = [];
	for (const row_data of r.message) {
		const row = frappe.model.add_child(
			frm.doc,
			"Annual Assessment Row",
			"assessment_rows"
		);
		Object.assign(row, row_data);
	}

	frm.refresh_field("assessment_rows");
	frm.dirty();

	frappe.show_alert({
		message: __("{0} linha(s) calculada(s). Guarde o documento para confirmar.", [
			r.message.length,
		]),
		indicator: "green",
	});
}
