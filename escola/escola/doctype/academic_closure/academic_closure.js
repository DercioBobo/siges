frappe.ui.form.on("Academic Closure", {
	onload(frm) {
		escola.utils.auto_fill_academic_year(frm);
	},

	refresh(frm) {
		set_queries(frm);

		const grid = frm.fields_dict["closure_rows"] && frm.fields_dict["closure_rows"].grid;
		if (grid) {
			grid.cannot_add_rows = true;
			grid.cannot_delete_rows = true;
		}

		frm.add_custom_button(__("Carregar Promoções"), () => _load_promotions(frm));

		if (!frm.doc.__islocal) {
			frm.add_custom_button(__("Sincronizar Alunos"), () => _sync_closure_students(frm));
		}

		if (!frm.doc.__islocal && frm.doc.closure_rows && frm.doc.closure_rows.length > 0) {
			frm.add_custom_button(__("Criar Boletins"), () => {
				frappe.confirm(
					__("Serão criados Boletins para os alunos desta turma que ainda não tenham um. Continuar?"),
					() => {
						frappe.call({
							method: "escola.escola.doctype.academic_closure.academic_closure.create_report_cards",
							args:   { doc_name: frm.doc.name },
							freeze: true,
							freeze_message: __("A criar/actualizar Boletins…"),
							callback(r) {
								if (r.exc) return;
								const msg = r.message;
								if (msg.error === "no_closure_rows") {
									frappe.msgprint(__("Não existem alunos no Fecho para criar Boletins."));
									return;
								}
								if (msg.error === "no_annual_assessment") {
									frappe.msgprint(__("Não existe Avaliação Anual para esta Turma e Ano Lectivo."));
									return;
								}
								const created = (msg.created || []).length;
								const updated = (msg.updated || []).length;
								const errors  = (msg.errors  || []).length;
								if (created > 0 || updated > 0) {
									let text = __("{0} Boletim(ns) criado(s), {1} actualizado(s).", [created, updated]);
									if (errors) text += " " + __("{0} erro(s) — verifique os logs.", [errors]);
									frappe.show_alert({ message: text, indicator: "green" });
								} else if (errors > 0) {
									frappe.msgprint(__("{0} erro(s) ao processar Boletins. Verifique os logs do servidor.", [errors]));
								} else {
									frappe.msgprint(__("Nenhum Boletim processado."));
								}
							},
						});
					}
				);
			}, __("Acções"));
		}
	},

	// Turma is the entry point — fills Classe and Ano Lectivo, then auto-loads
	async class_group(frm) {
		if (!frm.doc.class_group) {
			frm.set_value("school_class",  null);
			frm.set_value("academic_year", null);
			set_queries(frm);
			return;
		}

		const cg = await frappe.db.get_value(
			"Class Group", frm.doc.class_group, ["academic_year", "school_class"]
		);
		if (cg) {
			frm.set_value("school_class",  cg.school_class  || null);
			frm.set_value("academic_year", cg.academic_year || null);
		}
		set_queries(frm);

		// Auto-load promotions immediately if we have both fields
		if (frm.doc.class_group && frm.doc.academic_year) {
			_try_auto_load(frm);
		}
	},

	academic_year(frm) {
		if (!frm.doc.class_group) frm.set_value("school_class", null);
		set_queries(frm);
	},
});

// ---------------------------------------------------------------------------
// Sync students
// ---------------------------------------------------------------------------

function _sync_closure_students(frm) {
	frappe.confirm(
		__("Alunos sem estado 'Activo' serão removidos. As decisões dos restantes são preservadas. Continuar?"),
		() => {
			frappe.call({
				method: "escola.escola.doctype.academic_closure.academic_closure.sync_academic_closure_students",
				args: { doc_name: frm.doc.name },
				freeze: true,
				freeze_message: __("A sincronizar alunos…"),
				callback(r) {
					if (!r.message) return;
					const { removed, kept } = r.message;
					if (removed > 0) {
						frappe.show_alert({
							message: __("{0} aluno(s) removido(s), {1} mantido(s).", [removed, kept]),
							indicator: "orange",
						});
						frm.reload_doc();
					} else {
						frappe.show_alert({
							message: __("Todos os alunos estão activos. Nenhuma alteração."),
							indicator: "green",
						});
					}
				},
			});
		}
	);
}

// ---------------------------------------------------------------------------

function set_queries(frm) {
	const cg_filters = { is_active: 1 };
	if (frm.doc.academic_year) cg_filters.academic_year = frm.doc.academic_year;
	if (frm.doc.school_class)  cg_filters.school_class  = frm.doc.school_class;
	frm.set_query("class_group",  () => ({ filters: cg_filters }));
	frm.set_query("school_class", () => ({ filters: { is_active: 1 } }));
}

// ---------------------------------------------------------------------------
// Auto-load on class_group change (silent — no confirm, no error dialogs)
// ---------------------------------------------------------------------------

async function _try_auto_load(frm) {
	// Only auto-load when the table is empty (don't clobber existing data)
	if (frm.doc.closure_rows && frm.doc.closure_rows.length > 0) return;

	const r = await frappe.call({
		method: "escola.escola.doctype.academic_closure.academic_closure.load_promotions_by_params",
		args: {
			class_group:   frm.doc.class_group,
			academic_year: frm.doc.academic_year,
		},
	});

	if (r.exc || !r.message) return;
	const data = r.message;

	// If no promotion exists yet, just leave the table empty — user will fill later
	if (data.error) return;

	_apply_promotion_data(frm, data, /* silent */ true);
}

// ---------------------------------------------------------------------------
// Manual load (button) — confirms before overwriting, shows errors
// ---------------------------------------------------------------------------

function _load_promotions(frm) {
	if (!frm.doc.academic_year || !frm.doc.class_group) {
		frappe.msgprint(__("Por favor, preencha a Turma antes de carregar."));
		return;
	}

	const do_load = () => {
		// Use doc_name if saved, otherwise use params directly
		const method = frm.doc.__islocal
			? "escola.escola.doctype.academic_closure.academic_closure.load_promotions_by_params"
			: "escola.escola.doctype.academic_closure.academic_closure.load_promotions";
		const args = frm.doc.__islocal
			? { class_group: frm.doc.class_group, academic_year: frm.doc.academic_year }
			: { doc_name: frm.doc.name };

		frappe.call({
			method, args,
			freeze: true,
			freeze_message: __("A carregar promoções…"),
			callback(r) {
				if (!r.exc) _apply_promotion_data(frm, r.message, false);
			},
		});
	};

	if (frm.doc.closure_rows && frm.doc.closure_rows.length > 0) {
		frappe.confirm(__("Já existem dados no Fecho. Deseja substituir os dados actuais?"), do_load);
	} else {
		do_load();
	}
}

// ---------------------------------------------------------------------------

function _apply_promotion_data(frm, data, silent) {
	if (!data) return;

	if (data.error === "no_promotion") {
		if (!silent) frappe.msgprint(__("Não existe Promoção de Alunos para esta Turma e Ano Lectivo."));
		return;
	}
	if (data.error === "no_rows") {
		if (!silent) frappe.msgprint(__("Não foram encontrados dados de promoção para esta Turma."));
		return;
	}

	frm.clear_table("closure_rows");
	(data.rows || []).forEach(row => {
		const child = frm.add_child("closure_rows");
		child.student              = row.student;
		child.final_decision       = row.final_decision;
		child.total_failed_subjects = row.total_failed_subjects;
		child.overall_average      = row.overall_average;
		child.remarks              = row.remarks || "";
	});

	frm.refresh_field("closure_rows");
	frm.dirty();

	if (!silent) {
		frappe.show_alert({ message: __("Promoções carregadas com sucesso."), indicator: "green" });
	} else {
		frappe.show_alert({
			message: __("{0} aluno(s) carregado(s) da Promoção.", [(data.rows || []).length]),
			indicator: "green",
		}, 3);
	}
}
