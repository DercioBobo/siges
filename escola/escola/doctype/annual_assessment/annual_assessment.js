// Copyright (c) 2024, EntreTech and contributors
// For license information, please see license.txt

// In-memory details cache (populated after Calcular Avaliação; lost on page reload)
let _cached_details = {};
let _cached_terms   = [];

frappe.ui.form.on("Annual Assessment", {
	onload(frm) {
		escola.utils.auto_fill_academic_year(frm);
	},

	refresh(frm) {
		set_queries(frm);

		const grid = frm.fields_dict["assessment_rows"] && frm.fields_dict["assessment_rows"].grid;
		if (grid) {
			grid.cannot_add_rows = true;
			grid.cannot_delete_rows = true;
		}

		if (!frm.is_new()) {
			frm.add_custom_button(__("Carregar Alunos"), () => load_students(frm));
			frm.add_custom_button(__("Sincronizar Alunos"), () => _sync_assessment_students(frm));
			frm.add_custom_button(__("Calcular Avaliação"), () => maybe_calculate(frm), null, "primary");
			frm.add_custom_button(__("Imprimir Mapa"), () => _print_mapa(frm));

			const has_results = (frm.doc.assessment_rows || []).some(r => r.result);
			if (has_results) {
				frm.add_custom_button(
					__("Iniciar Promoção →"),
					() => _launch_promotion(frm),
					null, "primary"
				);
			}

			_render_from_rows(frm);
		}
	},

	async class_group(frm) {
		set_queries(frm);
		if (!frm.doc.class_group) return;
		if (!frm.doc.academic_year) {
			const cg = await frappe.db.get_value("Class Group", frm.doc.class_group, ["academic_year"]);
			if (cg && cg.academic_year) frm.set_value("academic_year", cg.academic_year);
		}
		// Auto-load students on new docs when the table is empty
		if (frm.doc.__islocal && !(frm.doc.assessment_rows && frm.doc.assessment_rows.length)) {
			_auto_load_students(frm);
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
});

// ---------------------------------------------------------------------------
// Auto-load students (silent, for new docs)
// ---------------------------------------------------------------------------

async function _auto_load_students(frm) {
	if (!frm.doc.class_group) return;
	const r = await frappe.call({
		method: "escola.escola.doctype.annual_assessment.annual_assessment.get_students_for_assessment",
		args: { class_group: frm.doc.class_group },
	});
	if (!r.message || !r.message.length) return;
	frm.clear_table("assessment_rows");
	r.message.forEach(student => {
		const row = frappe.model.add_child(frm.doc, "Annual Assessment Row", "assessment_rows");
		row.student = student;
	});
	frm.refresh_field("assessment_rows");
	frappe.show_alert({
		message: __("{0} aluno(s) carregado(s).", [r.message.length]),
		indicator: "green",
	}, 3);
}

// ---------------------------------------------------------------------------
// Sync students
// ---------------------------------------------------------------------------

function _sync_assessment_students(frm) {
	frappe.confirm(
		__("Alunos sem estado 'Activo' serão removidos. As notas dos restantes são preservadas. Continuar?"),
		() => {
			frappe.call({
				method: "escola.escola.doctype.annual_assessment.annual_assessment.sync_annual_assessment_students",
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
// Queries
// ---------------------------------------------------------------------------

function set_queries(frm) {
	const cg_filters = { is_active: 1 };
	if (frm.doc.academic_year) cg_filters.academic_year = frm.doc.academic_year;
	if (frm.doc.school_class)  cg_filters.school_class  = frm.doc.school_class;
	frm.set_query("class_group", () => ({ filters: cg_filters }));
}

// ---------------------------------------------------------------------------
// Load students (no grades)
// ---------------------------------------------------------------------------

function load_students(frm) {
	if (!frm.doc.class_group) {
		frappe.msgprint(__("Seleccione a Turma antes de carregar alunos."));
		return;
	}
	if (frm.is_dirty() || frm.is_new()) {
		frappe.msgprint(__("Guarde o documento antes de carregar alunos."));
		return;
	}

	const has_rows = (frm.doc.assessment_rows || []).length > 0;
	const do_load = () => {
		frappe.call({
			method: "escola.escola.doctype.annual_assessment.annual_assessment.get_students_for_assessment",
			args: { class_group: frm.doc.class_group },
			callback(r) {
				if (!r.message || !r.message.length) {
					frappe.msgprint(__("Nenhum aluno activo encontrado nesta turma."));
					return;
				}
				frm.clear_table("assessment_rows");
				r.message.forEach(student => {
					const row = frappe.model.add_child(frm.doc, "Annual Assessment Row", "assessment_rows");
					row.student = student;
				});
				frm.refresh_field("assessment_rows");
				frm.dirty();
				frappe.show_alert({
					message: __("{0} aluno(s) carregado(s).", [r.message.length]),
					indicator: "green",
				});
			},
		});
	};

	if (has_rows) {
		frappe.confirm(
			__("Substituir os alunos e resultados actuais? Esta acção não pode ser revertida."),
			do_load
		);
	} else {
		do_load();
	}
}

// ---------------------------------------------------------------------------
// Calculate
// ---------------------------------------------------------------------------

function maybe_calculate(frm) {
	if (!frm.doc.academic_year || !frm.doc.class_group) {
		frappe.msgprint(__("Por favor, seleccione o Ano Lectivo e a Turma antes de calcular."));
		return;
	}
	if (frm.is_dirty() || frm.is_new()) {
		frappe.msgprint(__("Por favor, guarde o documento antes de calcular."));
		return;
	}

	const has_rows = (frm.doc.assessment_rows || []).length > 0;
	if (has_rows) {
		frappe.confirm(
			__("Já existem resultados. Recalcular irá substituir todos os valores actuais. Continuar?"),
			() => do_calculate(frm)
		);
	} else {
		do_calculate(frm);
	}
}

async function do_calculate(frm) {
	const r = await frappe.call({
		method: "escola.escola.doctype.annual_assessment.annual_assessment.calculate_assessment",
		args: { doc_name: frm.doc.name },
		freeze: true,
		freeze_message: __("A calcular avaliação…"),
	});

	if (!r.message) return;

	const msg = r.message;
	if (msg.error === "no_terms") {
		frappe.msgprint(__("Não existem Períodos Académicos para o Ano Lectivo <b>{0}</b>.", [frm.doc.academic_year]));
		return;
	}
	if (msg.error === "no_grade_entries") {
		frappe.msgprint(__("Não foram encontradas Pautas de Notas para a Turma <b>{0}</b>.", [frm.doc.class_group]));
		return;
	}
	if (msg.error === "no_grades") {
		frappe.msgprint(__("As Pautas de Notas desta turma não têm valores preenchidos."));
		return;
	}

	// Cache details for click-to-open modal
	_cached_details = msg.details || {};
	_cached_terms   = msg.terms   || [];

	frm.clear_table("assessment_rows");
	for (const row_data of msg.rows) {
		const row = frappe.model.add_child(frm.doc, "Annual Assessment Row", "assessment_rows");
		Object.assign(row, row_data);
	}
	frm.refresh_field("assessment_rows");

	_render_grades_html(frm, msg.rows, msg.details, msg.terms);
	frm.dirty();

	frappe.show_alert({
		message: __("{0} aluno(s) calculado(s). Guarde para confirmar.", [msg.rows.length]),
		indicator: "green",
	});
}

// ---------------------------------------------------------------------------
// HTML detail panel
// ---------------------------------------------------------------------------

function _render_from_rows(frm) {
	const rows = frm.doc.assessment_rows || [];
	if (!rows.length) {
		_set_html(frm, "");
		return;
	}
	_render_summary_html(frm, rows);
}

function _render_summary_html(frm, rows) {
	if (!rows || !rows.length) { _set_html(frm, ""); return; }

	const tbody = rows.map(r => {
		const avg = r.final_grade != null ? String(Math.round(parseFloat(r.final_grade))) : "—";
		const t1  = r.term_1_average != null ? String(Math.round(parseFloat(r.term_1_average))) : "—";
		const t2  = r.term_2_average != null ? String(Math.round(parseFloat(r.term_2_average))) : "—";
		const t3  = r.term_3_average != null ? String(Math.round(parseFloat(r.term_3_average))) : "—";
		const res = r.result || "—";
		const badge_color = res === "Aprovado" ? "#16a34a" : res === "Reprovado" ? "#dc2626" : "#6b7280";
		const badge_bg    = res === "Aprovado" ? "#dcfce7" : res === "Reprovado" ? "#fee2e2" : "#f3f4f6";
		const comp = r.comportamento_anual
			? `<span style="background:#ede9fe;color:#5b21b6;font-size:11px;font-weight:600;padding:2px 8px;border-radius:12px;">${frappe.utils.escape_html(__(r.comportamento_anual))}</span>`
			: "—";
		return `<tr>
			<td style="padding:7px 12px;">
				<button class="btn-student-detail" data-student="${frappe.utils.escape_html(r.student)}" data-doc="${frappe.utils.escape_html(frm.doc.name)}"
					style="background:none;border:none;padding:0;font-weight:600;color:#2563eb;cursor:pointer;font-size:13px;text-decoration:underline;text-underline-offset:2px;">
					${frappe.utils.escape_html(r.student)}
				</button>
			</td>
			<td style="padding:7px 12px;text-align:center;">${t1}</td>
			<td style="padding:7px 12px;text-align:center;">${t2}</td>
			<td style="padding:7px 12px;text-align:center;">${t3}</td>
			<td style="padding:7px 12px;text-align:center;font-weight:600;">${avg}</td>
			<td style="padding:7px 12px;text-align:center;">
				<span style="background:${badge_bg};color:${badge_color};font-size:11px;font-weight:600;padding:2px 8px;border-radius:12px;">${__(res)}</span>
			</td>
			<td style="padding:7px 12px;text-align:center;color:#6b7280;">${r.total_absences != null ? r.total_absences : "—"}</td>
			<td style="padding:7px 12px;text-align:center;">${comp}</td>
		</tr>`;
	}).join("");

	const html = `
<div style="overflow-x:auto;">
<table style="width:100%;border-collapse:collapse;font-size:13px;">
  <thead>
    <tr style="background:#f1f5f9;">
      <th style="padding:8px 12px;text-align:left;font-size:11px;font-weight:600;color:#475569;text-transform:uppercase;letter-spacing:0.04em;border-bottom:2px solid #e2e8f0;">${__("Aluno")}</th>
      <th style="padding:8px 12px;text-align:center;font-size:11px;font-weight:600;color:#475569;text-transform:uppercase;letter-spacing:0.04em;border-bottom:2px solid #e2e8f0;">${__("T1")}</th>
      <th style="padding:8px 12px;text-align:center;font-size:11px;font-weight:600;color:#475569;text-transform:uppercase;letter-spacing:0.04em;border-bottom:2px solid #e2e8f0;">${__("T2")}</th>
      <th style="padding:8px 12px;text-align:center;font-size:11px;font-weight:600;color:#475569;text-transform:uppercase;letter-spacing:0.04em;border-bottom:2px solid #e2e8f0;">${__("T3")}</th>
      <th style="padding:8px 12px;text-align:center;font-size:11px;font-weight:600;color:#475569;text-transform:uppercase;letter-spacing:0.04em;border-bottom:2px solid #e2e8f0;">${__("Média")}</th>
      <th style="padding:8px 12px;text-align:center;font-size:11px;font-weight:600;color:#475569;text-transform:uppercase;letter-spacing:0.04em;border-bottom:2px solid #e2e8f0;">${__("Resultado")}</th>
      <th style="padding:8px 12px;text-align:center;font-size:11px;font-weight:600;color:#475569;text-transform:uppercase;letter-spacing:0.04em;border-bottom:2px solid #e2e8f0;">${__("Faltas")}</th>
      <th style="padding:8px 12px;text-align:center;font-size:11px;font-weight:600;color:#475569;text-transform:uppercase;letter-spacing:0.04em;border-bottom:2px solid #e2e8f0;">${__("Comportamento")}</th>
    </tr>
  </thead>
  <tbody>${tbody}</tbody>
</table>
</div>`;

	_set_html(frm, html);
	_bind_student_clicks(frm);
}

function _render_grades_html(frm, rows, details, terms) {
	if (!rows || !rows.length) { _set_html(frm, ""); return; }

	const t_labels = terms || ["T1", "T2", "T3"];

	const tbody = rows.map(r => {
		const avg = r.final_grade != null ? String(Math.round(parseFloat(r.final_grade))) : "—";
		const t1  = r.term_1_average != null ? String(Math.round(parseFloat(r.term_1_average))) : "—";
		const t2  = r.term_2_average != null ? String(Math.round(parseFloat(r.term_2_average))) : "—";
		const t3  = r.term_3_average != null ? String(Math.round(parseFloat(r.term_3_average))) : "—";
		const res = r.result || "—";
		const badge_color = res === "Aprovado" ? "#16a34a" : res === "Reprovado" ? "#dc2626" : "#6b7280";
		const badge_bg    = res === "Aprovado" ? "#dcfce7" : res === "Reprovado" ? "#fee2e2" : "#f3f4f6";
		const comp = r.comportamento_anual
			? `<span style="background:#ede9fe;color:#5b21b6;font-size:11px;font-weight:600;padding:2px 8px;border-radius:12px;">${frappe.utils.escape_html(__(r.comportamento_anual))}</span>`
			: "—";
		return `<tr>
			<td style="padding:7px 12px;">
				<button class="btn-student-detail" data-student="${frappe.utils.escape_html(r.student)}" data-doc="${frappe.utils.escape_html(frm.doc.name)}"
					style="background:none;border:none;padding:0;font-weight:600;color:#2563eb;cursor:pointer;font-size:13px;text-decoration:underline;text-underline-offset:2px;">
					${frappe.utils.escape_html(r.student)}
				</button>
			</td>
			<td style="padding:7px 12px;text-align:center;">${t1}</td>
			<td style="padding:7px 12px;text-align:center;">${t2}</td>
			<td style="padding:7px 12px;text-align:center;">${t3}</td>
			<td style="padding:7px 12px;text-align:center;font-weight:600;">${avg}</td>
			<td style="padding:7px 12px;text-align:center;">
				<span style="background:${badge_bg};color:${badge_color};font-size:11px;font-weight:600;padding:2px 8px;border-radius:12px;">${__(res)}</span>
			</td>
			<td style="padding:7px 12px;text-align:center;color:#6b7280;">${r.total_absences != null ? r.total_absences : "—"}</td>
			<td style="padding:7px 12px;text-align:center;">${comp}</td>
		</tr>`;
	}).join("");

	const html = `
<div style="overflow-x:auto;">
<table style="width:100%;border-collapse:collapse;font-size:13px;">
  <thead>
    <tr style="background:#f1f5f9;">
      <th style="padding:8px 12px;text-align:left;font-size:11px;font-weight:600;color:#475569;text-transform:uppercase;letter-spacing:0.04em;border-bottom:2px solid #e2e8f0;">${__("Aluno")}</th>
      <th style="padding:8px 12px;text-align:center;font-size:11px;font-weight:600;color:#475569;text-transform:uppercase;letter-spacing:0.04em;border-bottom:2px solid #e2e8f0;">${__("T1")}</th>
      <th style="padding:8px 12px;text-align:center;font-size:11px;font-weight:600;color:#475569;text-transform:uppercase;letter-spacing:0.04em;border-bottom:2px solid #e2e8f0;">${__("T2")}</th>
      <th style="padding:8px 12px;text-align:center;font-size:11px;font-weight:600;color:#475569;text-transform:uppercase;letter-spacing:0.04em;border-bottom:2px solid #e2e8f0;">${__("T3")}</th>
      <th style="padding:8px 12px;text-align:center;font-size:11px;font-weight:600;color:#475569;text-transform:uppercase;letter-spacing:0.04em;border-bottom:2px solid #e2e8f0;">${__("Média Geral")}</th>
      <th style="padding:8px 12px;text-align:center;font-size:11px;font-weight:600;color:#475569;text-transform:uppercase;letter-spacing:0.04em;border-bottom:2px solid #e2e8f0;">${__("Resultado")}</th>
      <th style="padding:8px 12px;text-align:center;font-size:11px;font-weight:600;color:#475569;text-transform:uppercase;letter-spacing:0.04em;border-bottom:2px solid #e2e8f0;">${__("Faltas")}</th>
      <th style="padding:8px 12px;text-align:center;font-size:11px;font-weight:600;color:#475569;text-transform:uppercase;letter-spacing:0.04em;border-bottom:2px solid #e2e8f0;">${__("Comportamento")}</th>
    </tr>
  </thead>
  <tbody>${tbody}</tbody>
</table>
</div>`;

	_set_html(frm, html);
	_bind_student_clicks(frm);
}

// ---------------------------------------------------------------------------
// Student click binding
// ---------------------------------------------------------------------------

function _bind_student_clicks(frm) {
	const fd = frm.fields_dict["grades_detail_html"];
	if (!fd) return;
	fd.$wrapper.find(".btn-student-detail").off("click").on("click", function () {
		const student = $(this).data("student");
		const doc_name = $(this).data("doc");
		_open_student_modal(student, doc_name);
	});
}

function _open_student_modal(student, doc_name) {
	// Use cached details if available (after Calcular), otherwise fetch from server
	if (_cached_details[student]) {
		const row = null; // row data not needed separately since detail has everything
		_show_student_dialog(student, _cached_details[student], _cached_terms, null);
	} else {
		frappe.call({
			method: "escola.escola.doctype.annual_assessment.annual_assessment.get_student_assessment_detail",
			args: { doc_name, student },
			freeze: true,
			freeze_message: __("A carregar detalhes…"),
			callback(r) {
				if (!r.message || r.message.error) {
					frappe.msgprint(__("Não foi possível carregar os detalhes do aluno."));
					return;
				}
				_cached_details[student] = r.message.detail;
				_cached_terms = r.message.terms || [];
				_show_student_dialog(student, r.message.detail, r.message.terms, r.message.row);
			},
		});
	}
}

function _show_student_dialog(student, detail, terms, row_data) {
	const t_labels = terms && terms.length ? terms : ["T1", "T2", "T3"];
	const subjects = detail ? Object.keys(detail).sort() : [];
	const fmt = v => (v != null ? String(Math.round(parseFloat(v))) : "—");

	// Compute row summary from detail if row_data not passed
	let final_avg = "—", result_label = "—", result_color = "#6b7280", result_bg = "#f3f4f6";
	let term_avgs = [];
	if (subjects.length) {
		const n_terms = t_labels.length;
		for (let i = 1; i <= n_terms; i++) {
			const key = `t${i}`;
			const vals = subjects.map(s => detail[s][key]).filter(v => v != null);
			if (vals.length) term_avgs.push(round2(vals.reduce((a, b) => a + b, 0) / vals.length));
			else term_avgs.push(null);
		}
		const valid = term_avgs.filter(v => v != null);
		if (valid.length) final_avg = fmt(valid.reduce((a, b) => a + b, 0) / valid.length);
	}
	if (row_data) {
		final_avg = fmt(row_data.final_grade);
		const res = row_data.result || "";
		result_label = res || "—";
		result_color = res === "Aprovado" ? "#16a34a" : res === "Reprovado" ? "#dc2626" : "#6b7280";
		result_bg    = res === "Aprovado" ? "#dcfce7" : res === "Reprovado" ? "#fee2e2" : "#f3f4f6";
	}

	// Build subject rows
	const subject_rows_html = subjects.map(subj => {
		const d = detail[subj];
		const avg_val = d.avg != null ? parseFloat(d.avg) : null;
		const avg_color = avg_val != null && avg_val < 10 ? "#dc2626" : avg_val != null && avg_val >= 10 ? "#16a34a" : "#374151";
		const term_cells = t_labels.map((_, i) => {
			const v = d[`t${i + 1}`];
			const color = v != null && parseFloat(v) < 10 ? "#dc2626" : v != null ? "#374151" : "#9ca3af";
			return `<td style="padding:10px 14px;text-align:center;font-size:13px;color:${color};font-weight:${v != null ? '500' : '400'};">${fmt(v)}</td>`;
		}).join("");
		return `<tr style="border-bottom:1px solid #f1f5f9;">
			<td style="padding:10px 14px;font-size:13px;color:#374151;font-weight:500;">${frappe.utils.escape_html(subj)}</td>
			${term_cells}
			<td style="padding:10px 14px;text-align:center;font-size:13px;font-weight:700;color:${avg_color};">${fmt(avg_val)}</td>
		</tr>`;
	}).join("");

	// Totals row
	const total_cells = t_labels.map((_, i) => {
		const v = term_avgs[i];
		return `<td style="padding:10px 14px;text-align:center;font-size:13px;font-weight:700;color:#1e40af;">${fmt(v)}</td>`;
	}).join("");

	const totals_row_html = `<tr style="background:linear-gradient(to right,#eff6ff,#f0f9ff);border-top:2px solid #bfdbfe;">
		<td style="padding:10px 14px;font-size:13px;font-weight:700;color:#1e40af;">${__("Média Geral")}</td>
		${total_cells}
		<td style="padding:10px 14px;text-align:center;font-size:15px;font-weight:800;color:#1e40af;">${final_avg}</td>
	</tr>`;

	const term_headers = t_labels.map(tl =>
		`<th style="padding:10px 14px;text-align:center;font-size:11px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:0.06em;">${frappe.utils.escape_html(tl)}</th>`
	).join("");

	const absences_html = row_data && row_data.total_absences != null
		? `<div style="display:flex;align-items:center;gap:6px;background:#fff7ed;border:1px solid #fed7aa;border-radius:8px;padding:8px 14px;font-size:13px;color:#92400e;">
				<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
				<span>${__("Total de faltas")}: <b>${row_data.total_absences}</b></span>
			</div>`
		: "";

	const no_data_html = !subjects.length
		? `<div style="text-align:center;padding:32px;color:#9ca3af;font-size:14px;">${__("Sem notas registadas para este aluno.")}</div>`
		: "";

	const body_html = `
<div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
  <!-- Header card -->
  <div style="background:linear-gradient(135deg,#1e40af 0%,#3b82f6 100%);border-radius:12px;padding:20px 24px;margin-bottom:20px;color:#fff;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px;">
    <div>
      <div style="font-size:11px;font-weight:600;letter-spacing:0.08em;text-transform:uppercase;opacity:0.75;margin-bottom:4px;">${__("Aluno")}</div>
      <div style="font-size:20px;font-weight:700;line-height:1.2;">${frappe.utils.escape_html(student)}</div>
    </div>
    <div style="display:flex;gap:16px;flex-wrap:wrap;">
      <div style="text-align:center;">
        <div style="font-size:11px;font-weight:600;letter-spacing:0.06em;text-transform:uppercase;opacity:0.75;margin-bottom:2px;">${__("Média Final")}</div>
        <div style="font-size:28px;font-weight:800;line-height:1;">${final_avg}</div>
      </div>
      ${result_label !== "—" ? `<div style="display:flex;align-items:center;">
        <span style="background:${result_bg};color:${result_color};font-size:13px;font-weight:700;padding:6px 16px;border-radius:20px;">${__(result_label)}</span>
      </div>` : ""}
    </div>
  </div>

  ${absences_html ? `<div style="margin-bottom:16px;">${absences_html}</div>` : ""}

  ${subjects.length ? `
  <!-- Subject table -->
  <div style="border:1px solid #e2e8f0;border-radius:12px;overflow:hidden;">
    <table style="width:100%;border-collapse:collapse;">
      <thead>
        <tr style="background:#f8fafc;border-bottom:2px solid #e2e8f0;">
          <th style="padding:10px 14px;text-align:left;font-size:11px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:0.06em;">${__("Disciplina")}</th>
          ${term_headers}
          <th style="padding:10px 14px;text-align:center;font-size:11px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:0.06em;">${__("Média")}</th>
        </tr>
      </thead>
      <tbody>
        ${subject_rows_html}
        ${totals_row_html}
      </tbody>
    </table>
  </div>` : no_data_html}
</div>`;

	const d = new frappe.ui.Dialog({
		title: __("Detalhe de Avaliação"),
		size: "large",
	});
	d.body.innerHTML = body_html;
	d.show();
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function round2(v) { return Math.round(v * 100) / 100; }

function _set_html(frm, html) {
	const fd = frm.fields_dict["grades_detail_html"];
	if (fd) fd.$wrapper.html(html);
}

// ---------------------------------------------------------------------------
// Launch Student Promotion (one-click flow)
// ---------------------------------------------------------------------------

async function _launch_promotion(frm) {
	const r = await frappe.call({
		method: "escola.escola.doctype.annual_assessment.annual_assessment.create_or_get_promotion",
		args:   { annual_assessment_name: frm.doc.name },
		freeze: true,
		freeze_message: __("A preparar promoção…"),
	});
	if (!r.message) return;

	const { name, is_new, status } = r.message;

	if (!is_new) {
		frappe.show_alert({
			message: __("Promoção já existe — <b>{0}</b>. A abrir…", [name]),
			indicator: "blue",
		}, 3);
	} else {
		frappe.show_alert({
			message: __("Promoção <b>{0}</b> criada com {1} linha(s).",
				[name, r.message.row_count || ""]),
			indicator: "green",
		}, 3);
	}

	// Signal to Student Promotion to auto-open the distribution modal
	if (status !== "Finalizado" && status !== "Bloqueado") {
		frappe.flags.sp_auto_distribute = true;
	}
	frappe.set_route("Form", "Student Promotion", name);
}

// ---------------------------------------------------------------------------
// Imprimir Mapa de Aproveitamento
// ---------------------------------------------------------------------------

function _print_mapa(frm) {
	if (!frm.doc.academic_year || !frm.doc.class_group) {
		frappe.msgprint(__("Seleccione o Ano Lectivo e a Turma antes de imprimir."));
		return;
	}
	frappe.call({
		method: "escola.escola.doctype.annual_assessment.annual_assessment.get_mapa_print_data",
		args: { doc_name: frm.doc.name },
		freeze: true,
		freeze_message: __("A preparar impressão…"),
		callback(r) {
			if (!r.message) return;
			_open_mapa_print_window(r.message);
		},
	});
}

function _open_mapa_print_window(data) {
	const html = _build_mapa_html(data);
	const w = window.open("", "_blank");
	if (!w) { frappe.msgprint(__("Não foi possível abrir a janela de impressão.")); return; }
	w.document.write(html);
	w.document.close();
	w.focus();
	setTimeout(() => w.print(), 600);
}

function _build_mapa_html(d) {
	const fmt = (v) => (v !== null && v !== undefined) ? String(Math.round(parseFloat(v))) : "—";
	const _e  = (v) => frappe.utils.escape_html(v || "");
	const subjects = d.subjects || [];
	const terms    = d.terms    || [];
	const rows     = d.rows     || [];

	// Estimate table width vs. A4 landscape content area (~1020px at 96dpi with 10mm margins)
	// Nº(24) + Name(130) + per-subject(terms*26 + 32) + AF(36) + Resultado(60) + Faltas(28) + Comp(60)
	const est_width = 24 + 130 + subjects.length * (terms.length * 26 + 32) + 36 + 60 + 28 + 60;
	const scale = est_width > 1020 ? +(1020 / est_width).toFixed(3) : 1;

	// Build column headers: per subject show T1/T2/T3 subcolumns + AF
	const subj_header_row1 = subjects.map(s =>
		`<th colspan="${terms.length + 1}" style="border:1px solid #ccc;padding:4px 6px;
		            background:#1E293B;color:white;text-align:center;font-size:10px;white-space:nowrap;">
			${_e(s.label)}
		</th>`
	).join("");

	const subj_header_row2 = subjects.map(() =>
		terms.map((t, i) =>
			`<th style="border:1px solid #ccc;padding:3px 4px;background:#334155;color:white;
			            text-align:center;font-size:9px;min-width:32px;">${t.label}</th>`
		).join("") +
		`<th style="border:1px solid #ccc;padding:3px 4px;background:#475569;color:white;
		            text-align:center;font-size:9px;min-width:34px;font-weight:800;">MG</th>`
	).join("");

	// Data rows
	const body_rows = rows.map(r => {
		const subj_cells = subjects.map(s => {
			const sd = (r.subject_data || {})[s.name] || {};
			const term_cells = (sd.terms || []).map(v => {
				const n = v !== null && v !== undefined ? parseFloat(v) : null;
				const color = n !== null ? (n >= 10 ? "#166534" : "#991B1B") : "#9CA3AF";
				return `<td style="border:1px solid #E5E7EB;padding:3px 4px;text-align:center;
				             font-size:10px;color:${color};">${n !== null ? String(Math.round(n)) : "—"}</td>`;
			}).join("");
			const af_n = sd.af !== null && sd.af !== undefined ? parseFloat(sd.af) : null;
			const af_color = af_n !== null ? (af_n >= 10 ? "#166534" : "#991B1B") : "#9CA3AF";
			const af_bg    = af_n !== null ? (af_n >= 10 ? "#F0FDF4" : "#FEF2F2") : "white";
			return term_cells +
				`<td style="border:1px solid #E5E7EB;padding:3px 4px;text-align:center;
				     font-size:10px;font-weight:700;background:${af_bg};color:${af_color};">
					${af_n !== null ? String(Math.round(af_n)) : "—"}
				</td>`;
		}).join("");

		const fg_n  = r.final_grade !== null && r.final_grade !== undefined ? parseFloat(r.final_grade) : null;
		const fg_color  = fg_n !== null ? (fg_n >= 10 ? "#166534" : "#991B1B") : "#9CA3AF";
		const fg_bg     = fg_n !== null ? (fg_n >= 10 ? "#DCFCE7" : "#FEE2E2") : "white";
		const res = r.result || "—";
		const res_color = res === "Aprovado" ? "#166534" : res === "Reprovado" ? "#991B1B" : "#374151";
		const res_bg    = res === "Aprovado" ? "#DCFCE7" : res === "Reprovado" ? "#FEE2E2" : "#F9FAFB";

		return `<tr style="border-bottom:1px solid #F3F4F6;">
			<td style="border:1px solid #E5E7EB;padding:3px 5px;text-align:center;font-size:10px;color:#9CA3AF;">${r.idx}</td>
			<td style="border:1px solid #E5E7EB;padding:3px 6px;font-size:10px;font-weight:500;white-space:nowrap;max-width:160px;overflow:hidden;text-overflow:ellipsis;"
			    title="${frappe.utils.escape_html(r.student_name || "")}">${frappe.utils.escape_html(r.student_name || r.student)}</td>
			${subj_cells}
			<td style="border:1px solid #E5E7EB;padding:3px 5px;text-align:center;font-size:11px;
			     font-weight:800;background:${fg_bg};color:${fg_color};">${fg_n !== null ? String(Math.round(fg_n)) : "—"}</td>
			<td style="border:1px solid #E5E7EB;padding:3px 5px;text-align:center;font-size:9px;
			     font-weight:700;background:${res_bg};color:${res_color};">${res}</td>
			<td style="border:1px solid #E5E7EB;padding:3px 5px;text-align:center;font-size:10px;color:#6B7280;">${r.total_absences !== null && r.total_absences !== undefined ? r.total_absences : "—"}</td>
			<td style="border:1px solid #E5E7EB;padding:3px 5px;text-align:center;font-size:9px;color:#7C3AED;">${r.comportamento || "—"}</td>
		</tr>`;
	}).join("");

	// Summary footer
	const approved = rows.filter(r => r.result === "Aprovado").length;
	const failed   = rows.filter(r => r.result === "Reprovado").length;
	const total    = rows.length;

	return `<!DOCTYPE html>
<html lang="pt">
<head>
<meta charset="UTF-8">
<title>Mapa de Aproveitamento — ${_e(d.class_group_name)}</title>
<style>
  @page { size: A4 landscape; margin: 10mm; }
  body { font-family: Arial, sans-serif; font-size: 11px; color: #111; margin: 0; padding: 0; }
  table { border-collapse: collapse; width: 100%; }
  @media print {
    body { -webkit-print-color-adjust: exact; print-color-adjust: exact; zoom: ${scale}; }
  }
</style>
</head>
<body>
  <!-- Header -->
  <div style="text-align:center;margin-bottom:8px;border-bottom:2px solid #1E293B;padding-bottom:6px;">
    <div style="font-size:14px;font-weight:800;text-transform:uppercase;letter-spacing:1px;">
      ${_e(d.school_name)}
    </div>
    <div style="font-size:12px;font-weight:700;margin-top:2px;">
      Mapa de Aproveitamento Pedagógico
    </div>
    <div style="font-size:10px;color:#6B7280;margin-top:4px;display:flex;justify-content:center;gap:24px;flex-wrap:wrap;">
      <span><b>Turma:</b> ${_e(d.class_group_name)}</span>
      <span><b>Ano Lectivo:</b> ${_e(d.academic_year)}</span>
      ${d.teacher_name ? `<span><b>Director(a) de Turma:</b> ${_e(d.teacher_name)}</span>` : ""}
      <span><b>Total de Alunos:</b> ${total}</span>
    </div>
  </div>

  <!-- Grade table -->
  <table>
    <thead>
      <tr>
        <th rowspan="2" style="border:1px solid #ccc;padding:4px;background:#F1F5F9;font-size:10px;text-align:center;min-width:24px;">Nº</th>
        <th rowspan="2" style="border:1px solid #ccc;padding:4px;background:#F1F5F9;font-size:10px;text-align:left;min-width:130px;">Nome Completo</th>
        ${subj_header_row1}
        <th rowspan="2" style="border:1px solid #ccc;padding:4px;background:#0F172A;color:white;font-size:10px;text-align:center;min-width:36px;">MG</th>
        <th rowspan="2" style="border:1px solid #ccc;padding:4px;background:#0F172A;color:white;font-size:10px;text-align:center;min-width:60px;">Resultado</th>
        <th rowspan="2" style="border:1px solid #ccc;padding:4px;background:#0F172A;color:white;font-size:10px;text-align:center;min-width:30px;">Faltas</th>
        <th rowspan="2" style="border:1px solid #ccc;padding:4px;background:#0F172A;color:white;font-size:10px;text-align:center;min-width:60px;">Comp.</th>
      </tr>
      <tr>${subj_header_row2}</tr>
    </thead>
    <tbody>${body_rows}</tbody>
  </table>

  <!-- Footer stats -->
  <div style="margin-top:10px;display:flex;gap:24px;font-size:10px;color:#374151;">
    <span><b style="color:#166534;">Aprovados:</b> ${approved}</span>
    <span><b style="color:#991B1B;">Reprovados:</b> ${failed}</span>
    <span><b>Total:</b> ${total}</span>
    <span style="margin-left:auto;color:#9CA3AF;">Impresso em ${new Date().toLocaleDateString('pt-MZ')}</span>
  </div>
</body>
</html>`;
}
