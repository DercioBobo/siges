// Copyright (c) 2024, EntreTech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Student Promotion", {
	refresh(frm) {
		set_queries(frm);

		frm.add_custom_button(__("Gerar Promoção"), () => {
			maybe_generate(frm);
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
}

function maybe_generate(frm) {
	if (!frm.doc.academic_year || !frm.doc.class_group) {
		frappe.msgprint(__("Por favor, seleccione o Ano Lectivo e a Turma."));
		return;
	}

	if (frm.is_dirty() || frm.is_new()) {
		frappe.msgprint(__("Por favor, guarde o documento antes de gerar a promoção."));
		return;
	}

	const has_rows = frm.doc.promotion_rows && frm.doc.promotion_rows.length > 0;

	if (has_rows) {
		frappe.confirm(
			__("Já existem decisões de promoção. Regenerar irá substituí-las. Continuar?"),
			() => do_generate(frm)
		);
	} else {
		do_generate(frm);
	}
}

async function do_generate(frm) {
	const r = await frappe.call({
		method:
			"escola.escola.doctype.student_promotion.student_promotion.generate_promotion",
		args: { doc_name: frm.doc.name },
		freeze: true,
		freeze_message: __("A gerar promoção…"),
	});

	if (!r.message) return;

	if (r.message.error === "no_annual_assessment") {
		frappe.msgprint(
			__("Não existe Avaliação Anual para esta turma. "
				+ "Calcule a Avaliação Anual antes de gerar a Promoção.")
		);
		return;
	}
	if (r.message.error === "no_rows") {
		frappe.msgprint(
			__("A Avaliação Anual desta turma não tem resultados calculados. "
				+ "Utilize o botão <b>Calcular Avaliação</b> na Avaliação Anual primeiro.")
		);
		return;
	}

	frm.doc.promotion_rows = [];
	for (const row_data of r.message) {
		const row = frappe.model.add_child(
			frm.doc,
			"Student Promotion Row",
			"promotion_rows"
		);
		Object.assign(row, row_data);
	}

	frm.refresh_field("promotion_rows");
	frm.dirty();

	frappe.show_alert({
		message: __("{0} aluno(s) processado(s). Guarde para confirmar.", [
			r.message.length,
		]),
		indicator: "green",
	});
}
