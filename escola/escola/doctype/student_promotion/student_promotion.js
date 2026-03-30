// Copyright (c) 2024, EntreTech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Student Promotion", {
	onload(frm) {
		escola.utils.auto_fill_academic_year(frm);
	},

	refresh(frm) {
		set_queries(frm);

		frm.add_custom_button(__("Gerar Promoção"), () => {
			maybe_generate(frm);
		});

		if (!frm.is_new()) {
			frm.add_custom_button(
				__("Gerar Inscrições Próximo Ano"),
				() => generate_enrollments(frm),
				__("Acções")
			);
		}
	},

	academic_year(frm) {
		frm.set_value("class_group", null);
		set_queries(frm);
	},

	school_class(frm) {
		frm.set_value("class_group", null);
		set_queries(frm);
	},

	next_academic_year(frm) {
		// Re-apply child row queries so next_class_group filters update
		set_queries(frm);
	},
});

frappe.ui.form.on("Student Promotion Row", {
	next_school_class(frm, cdt, cdn) {
		// Clear next_class_group when next_school_class changes
		frappe.model.set_value(cdt, cdn, "next_class_group", null);
	},
});

function set_queries(frm) {
	const cg_filters = { is_active: 1 };
	if (frm.doc.academic_year) cg_filters.academic_year = frm.doc.academic_year;
	if (frm.doc.school_class) cg_filters.school_class = frm.doc.school_class;
	frm.set_query("class_group", () => ({ filters: cg_filters }));

	frm.set_query("next_school_class", "promotion_rows", () => ({
		filters: { is_active: 1 },
	}));

	frm.set_query("next_class_group", "promotion_rows", (doc, cdt, cdn) => {
		const row = frappe.get_doc(cdt, cdn);
		const filters = { is_active: 1 };
		if (row.next_school_class) filters.school_class = row.next_school_class;
		if (doc.next_academic_year) filters.academic_year = doc.next_academic_year;
		return { filters };
	});
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
			__("Já existem decisões de promoção. Regenerar irá substituí-las "
				+ "(excepto as marcadas como Decisão Manual). Continuar?"),
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

function generate_enrollments(frm) {
	if (!frm.doc.next_academic_year) {
		frappe.msgprint(
			__("Defina o <b>Ano Lectivo Seguinte</b> no cabeçalho antes de continuar.")
		);
		return;
	}

	if (frm.is_dirty()) {
		frappe.msgprint(__("Por favor, guarde o documento antes de gerar inscrições."));
		return;
	}

	const promoted = (frm.doc.promotion_rows || []).filter(
		(r) => r.decision === "Promovido" || r.decision === "Concluído"
	);

	frappe.confirm(
		__(
			"Isto irá criar inscrições e alocações de turma para <b>{0}</b> aluno(s) "
			+ "com decisão Promovido / Concluído no ano lectivo <b>{1}</b>. Continuar?",
			[promoted.length, frm.doc.next_academic_year]
		),
		async () => {
			const r = await frappe.call({
				method:
					"escola.escola.doctype.student_promotion.student_promotion.generate_next_year_enrollments",
				args: { promotion_name: frm.doc.name },
				freeze: true,
				freeze_message: __("A criar inscrições…"),
			});

			if (!r.message) return;
			const m = r.message;

			let msg = __("Criadas: <b>{0}</b> | Ignoradas: <b>{1}</b>", [
				m.created,
				m.skipped,
			]);
			if (m.errors && m.errors.length) {
				msg += "<br><br><b>" + __("Avisos:") + "</b><br>"
					+ m.errors.join("<br>");
			}
			frappe.msgprint({
				title: __("Resultado"),
				message: msg,
				indicator: m.errors && m.errors.length ? "orange" : "green",
			});
			frm.reload_doc();
		}
	);
}
