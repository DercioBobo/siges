// Copyright (c) 2024, EntreTech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Annual Assessment", {
	onload(frm) {
		escola.utils.auto_fill_academic_year(frm);
	},

	refresh(frm) {
		set_queries(frm);

		if (!frm.is_new()) {
			frm.add_custom_button(__("Carregar Alunos"), () => load_students(frm), __("Acções"));
			frm.add_custom_button(__("Calcular Avaliação"), () => maybe_calculate(frm), __("Acções"));

			// Re-render detail panel from saved rows if details stored separately isn't feasible
			// render from child table data on refresh
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
	// On refresh: if we have rows but no details (details aren't stored), show a minimal summary
	const rows = frm.doc.assessment_rows || [];
	if (!rows.length) {
		_set_html(frm, "");
		return;
	}
	// Build a simple summary table from stored row data (no subject breakdown)
	_render_summary_html(frm, rows);
}

function _render_summary_html(frm, rows) {
	if (!rows || !rows.length) { _set_html(frm, ""); return; }

	const tbody = rows.map(r => {
		const avg = r.final_grade != null ? r.final_grade.toFixed(2) : "—";
		const t1  = r.term_1_average != null ? r.term_1_average.toFixed(2) : "—";
		const t2  = r.term_2_average != null ? r.term_2_average.toFixed(2) : "—";
		const t3  = r.term_3_average != null ? r.term_3_average.toFixed(2) : "—";
		const res = r.result || "—";
		const badge_color = res === "Aprovado" ? "#16a34a" : res === "Reprovado" ? "#dc2626" : "#6b7280";
		const badge_bg    = res === "Aprovado" ? "#dcfce7" : res === "Reprovado" ? "#fee2e2" : "#f3f4f6";
		return `<tr>
			<td style="padding:7px 12px;font-weight:500;">${frappe.utils.escape_html(r.student)}</td>
			<td style="padding:7px 12px;text-align:center;">${t1}</td>
			<td style="padding:7px 12px;text-align:center;">${t2}</td>
			<td style="padding:7px 12px;text-align:center;">${t3}</td>
			<td style="padding:7px 12px;text-align:center;font-weight:600;">${avg}</td>
			<td style="padding:7px 12px;text-align:center;">
				<span style="background:${badge_bg};color:${badge_color};font-size:11px;font-weight:600;padding:2px 8px;border-radius:12px;">${__(res)}</span>
			</td>
			<td style="padding:7px 12px;text-align:center;color:#6b7280;">${r.total_absences != null ? r.total_absences : "—"}</td>
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
    </tr>
  </thead>
  <tbody>${tbody}</tbody>
</table>
</div>
<p style="font-size:11px;color:#9ca3af;margin-top:8px;">
  ${__("Para ver o detalhe por disciplina, use <b>Calcular Avaliação</b>.")}
</p>`;
	_set_html(frm, html);
}

function _render_grades_html(frm, rows, details, terms) {
	if (!rows || !rows.length) { _set_html(frm, ""); return; }

	const t_labels = terms || ["T1", "T2", "T3"];

	const cards = rows.map(r => {
		const avg = r.final_grade != null ? r.final_grade.toFixed(2) : "—";
		const res = r.result || "";
		const badge_color = res === "Aprovado" ? "#16a34a" : res === "Reprovado" ? "#dc2626" : "#6b7280";
		const badge_bg    = res === "Aprovado" ? "#dcfce7" : res === "Reprovado" ? "#fee2e2" : "#f3f4f6";

		const subj_details = (details && details[r.student]) ? details[r.student] : {};
		const subjects = Object.keys(subj_details).sort();

		const subject_rows = subjects.map(subj => {
			const d = subj_details[subj];
			const fmt = v => (v != null ? v.toFixed(2) : "—");
			return `<tr>
				<td style="padding:5px 12px;">${frappe.utils.escape_html(subj)}</td>
				<td style="padding:5px 12px;text-align:center;">${fmt(d.t1)}</td>
				${t_labels.length >= 2 ? `<td style="padding:5px 12px;text-align:center;">${fmt(d.t2)}</td>` : ""}
				${t_labels.length >= 3 ? `<td style="padding:5px 12px;text-align:center;">${fmt(d.t3)}</td>` : ""}
				<td style="padding:5px 12px;text-align:center;font-weight:600;">${fmt(d.avg)}</td>
			</tr>`;
		}).join("");

		const totals_row = `<tr style="background:#f8fafc;border-top:2px solid #e2e8f0;">
			<td style="padding:6px 12px;font-weight:600;">${__("Média Geral")}</td>
			<td style="padding:6px 12px;text-align:center;font-weight:600;">${r.term_1_average != null ? r.term_1_average.toFixed(2) : "—"}</td>
			${t_labels.length >= 2 ? `<td style="padding:6px 12px;text-align:center;font-weight:600;">${r.term_2_average != null ? r.term_2_average.toFixed(2) : "—"}</td>` : ""}
			${t_labels.length >= 3 ? `<td style="padding:6px 12px;text-align:center;font-weight:600;">${r.term_3_average != null ? r.term_3_average.toFixed(2) : "—"}</td>` : ""}
			<td style="padding:6px 12px;text-align:center;font-weight:700;font-size:14px;">${avg}</td>
		</tr>`;

		const term_headers = t_labels.map((tl, i) =>
			`<th style="padding:7px 12px;text-align:center;font-size:11px;font-weight:600;color:#475569;text-transform:uppercase;letter-spacing:0.04em;">${frappe.utils.escape_html(tl)}</th>`
		).join("");

		return `
<div style="border:1px solid #e5e7eb;border-radius:8px;margin-bottom:14px;overflow:hidden;">
  <div style="background:#f8fafc;padding:10px 14px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid #e5e7eb;">
    <span style="font-weight:600;font-size:14px;">${frappe.utils.escape_html(r.student)}</span>
    <div style="display:flex;align-items:center;gap:12px;font-size:12px;color:#6b7280;">
      ${r.total_absences != null ? `<span>${__("Faltas")}: <b>${r.total_absences}</b></span>` : ""}
      <span>${__("Média")}: <b style="font-size:14px;color:#111;">${avg}</b></span>
      ${res ? `<span style="background:${badge_bg};color:${badge_color};font-size:11px;font-weight:600;padding:3px 10px;border-radius:12px;">${__(res)}</span>` : ""}
    </div>
  </div>
  ${subjects.length ? `
  <table style="width:100%;border-collapse:collapse;font-size:13px;">
    <thead>
      <tr style="background:#f1f5f9;">
        <th style="padding:7px 12px;text-align:left;font-size:11px;font-weight:600;color:#475569;text-transform:uppercase;letter-spacing:0.04em;">${__("Disciplina")}</th>
        ${term_headers}
        <th style="padding:7px 12px;text-align:center;font-size:11px;font-weight:600;color:#475569;text-transform:uppercase;letter-spacing:0.04em;">${__("Média")}</th>
      </tr>
    </thead>
    <tbody>
      ${subject_rows}
      ${totals_row}
    </tbody>
  </table>` : `<div style="padding:10px 14px;color:#9ca3af;font-size:12px;">${__("Sem notas lançadas para este aluno.")}</div>`}
</div>`;
	}).join("");

	_set_html(frm, cards);
}

function _set_html(frm, html) {
	const fd = frm.fields_dict["grades_detail_html"];
	if (fd) fd.$wrapper.html(html);
}
