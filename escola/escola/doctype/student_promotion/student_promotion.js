// Copyright (c) 2024, EntreTech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Student Promotion", {
	onload(frm) {
		escola.utils.auto_fill_academic_year(frm);
	},

	refresh(frm) {
		set_queries(frm);

		frm.add_custom_button(__("Gerar Promoção"), () => maybe_generate(frm));

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

	async class_group(frm) {
		set_queries(frm);
		if (!frm.doc.class_group) return;

		// Auto-fill academic_year and school_class from class_group
		const cg = await frappe.db.get_value(
			"Class Group", frm.doc.class_group, ["academic_year", "school_class"]
		);
		if (cg) {
			if (!frm.doc.academic_year && cg.academic_year)
				frm.set_value("academic_year", cg.academic_year);
			if (!frm.doc.school_class && cg.school_class)
				frm.set_value("school_class", cg.school_class);
		}
	},

	async school_class(frm) {
		set_queries(frm);
		// Populate next_school_class from next_class pointer
		if (frm.doc.school_class) {
			const sc = await frappe.db.get_value("School Class", frm.doc.school_class, "next_class");
			frm.set_value("next_school_class", sc || null);
		} else {
			frm.set_value("next_school_class", null);
		}
		frm.set_value("target_class_group", null);
		_auto_resolve_target(frm);
	},

	next_academic_year(frm) {
		set_queries(frm);
		frm.set_value("target_class_group", null);
		frm.set_value("retained_class_group", null);
		_auto_resolve_target(frm);
	},
});

// ---------------------------------------------------------------------------
// Queries
// ---------------------------------------------------------------------------

function set_queries(frm) {
	const cg_filters = { is_active: 1 };
	if (frm.doc.academic_year) cg_filters.academic_year = frm.doc.academic_year;
	if (frm.doc.school_class)  cg_filters.school_class  = frm.doc.school_class;
	frm.set_query("class_group", () => ({ filters: cg_filters }));

	// target_class_group: filtered by next_school_class + next_academic_year
	frm.set_query("target_class_group", () => {
		const f = { is_active: 1 };
		if (frm.doc.next_school_class)  f.school_class  = frm.doc.next_school_class;
		if (frm.doc.next_academic_year) f.academic_year = frm.doc.next_academic_year;
		return { filters: f };
	});

	// retained_class_group: same school_class, new academic_year
	frm.set_query("retained_class_group", () => {
		const f = { is_active: 1 };
		if (frm.doc.school_class)       f.school_class  = frm.doc.school_class;
		if (frm.doc.next_academic_year) f.academic_year = frm.doc.next_academic_year;
		return { filters: f };
	});
}

// ---------------------------------------------------------------------------
// Auto-resolve target_class_group when only one option exists
// ---------------------------------------------------------------------------

async function _auto_resolve_target(frm) {
	if (!frm.doc.next_academic_year) return;

	// Approved turma
	if (frm.doc.next_school_class && !frm.doc.target_class_group) {
		const cgs = await frappe.db.get_list("Class Group", {
			filters: {
				school_class:  frm.doc.next_school_class,
				academic_year: frm.doc.next_academic_year,
				is_active:     1,
			},
			fields: ["name"],
			limit: 2,
		});
		if (cgs.length === 1) frm.set_value("target_class_group", cgs[0].name);
	}

	// Retained turma (same class)
	if (frm.doc.school_class && !frm.doc.retained_class_group) {
		const cgs = await frappe.db.get_list("Class Group", {
			filters: {
				school_class:  frm.doc.school_class,
				academic_year: frm.doc.next_academic_year,
				is_active:     1,
			},
			fields: ["name"],
			limit: 2,
		});
		if (cgs.length === 1) frm.set_value("retained_class_group", cgs[0].name);
	}
}

// ---------------------------------------------------------------------------
// Generate promotion rows
// ---------------------------------------------------------------------------

function maybe_generate(frm) {
	if (!frm.doc.academic_year || !frm.doc.class_group) {
		frappe.msgprint(__("Por favor, seleccione o Ano Lectivo e a Turma."));
		return;
	}
	if (frm.is_dirty() || frm.is_new()) {
		frappe.msgprint(__("Por favor, guarde o documento antes de gerar a promoção."));
		return;
	}

	const has_rows = (frm.doc.promotion_rows || []).length > 0;
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
		method: "escola.escola.doctype.student_promotion.student_promotion.generate_promotion",
		args: { doc_name: frm.doc.name },
		freeze: true,
		freeze_message: __("A gerar promoção…"),
	});

	if (!r.message) return;
	const msg = r.message;

	if (msg.error === "no_annual_assessment") {
		frappe.msgprint(__("Não existe Avaliação Anual para esta turma. Calcule-a primeiro."));
		return;
	}
	if (msg.error === "no_rows") {
		frappe.msgprint(__("A Avaliação Anual não tem resultados. Use <b>Calcular Avaliação</b> primeiro."));
		return;
	}

	frm.clear_table("promotion_rows");
	for (const row_data of msg) {
		const row = frappe.model.add_child(frm.doc, "Student Promotion Row", "promotion_rows");
		Object.assign(row, row_data);
	}
	frm.refresh_field("promotion_rows");
	frm.dirty();

	const approved  = msg.filter(r => r.decision === "Aprovado" || r.decision === "Concluído").length;
	const retained  = msg.filter(r => r.decision === "Reprovado").length;
	frappe.show_alert({
		message: __("{0} aprovado(s) · {1} reprovado(s). Guarde para confirmar.", [approved, retained]),
		indicator: "green",
	});
}

// ---------------------------------------------------------------------------
// Generate enrollments
// ---------------------------------------------------------------------------

function generate_enrollments(frm) {
	if (!frm.doc.next_academic_year) {
		frappe.msgprint(__("Defina o <b>Ano Lectivo Seguinte</b> antes de continuar."));
		return;
	}
	if (!frm.doc.target_class_group && !frm.doc.retained_class_group) {
		frappe.msgprint(__("Defina a <b>Turma dos Aprovados</b> e/ou a <b>Turma dos Reprovados</b> antes de continuar."));
		return;
	}
	if (frm.is_dirty()) {
		frappe.msgprint(__("Guarde o documento antes de gerar inscrições."));
		return;
	}

	const rows = frm.doc.promotion_rows || [];
	const approved = rows.filter(r => r.decision === "Aprovado" || r.decision === "Concluído").length;
	const retained = rows.filter(r => r.decision === "Reprovado").length;

	frappe.confirm(
		__("Criar inscrições para <b>{0}</b> aprovado(s) e <b>{1}</b> reprovado(s) no ano <b>{2}</b>. Continuar?",
			[approved, retained, frm.doc.next_academic_year]),
		async () => {
			const r = await frappe.call({
				method: "escola.escola.doctype.student_promotion.student_promotion.generate_next_year_enrollments",
				args: { promotion_name: frm.doc.name },
				freeze: true,
				freeze_message: __("A criar inscrições…"),
			});
			if (!r.message) return;
			const m = r.message;
			let msg = __("Criadas: <b>{0}</b> | Ignoradas: <b>{1}</b>", [m.created, m.skipped]);
			if (m.errors && m.errors.length) {
				msg += "<br><br><b>" + __("Avisos:") + "</b><br>" + m.errors.join("<br>");
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
