// Copyright (c) 2024, EntreTech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Abertura de Ano Lectivo", {
	onload(frm) {
		if (frm.is_new() && !frm.doc.source_academic_year) {
			frappe.db.get_single_value("School Settings", "current_academic_year").then(val => {
				if (val) frm.set_value("source_academic_year", val);
			});
		}
	},

	refresh(frm) {
		if (frm.is_new()) {
			frm.add_custom_button(__("Verificar Pré-condições"), () => _run_preflight(frm));
		}

		if (frm.doc.docstatus === 1) {
			frm.dashboard.set_headline_alert(
				__("Ano lectivo <b>{0}</b> activado em {1}.", [
					frm.doc.target_academic_year,
					frappe.datetime.str_to_user(frm.doc.opening_date),
				]),
				"green"
			);
		}
	},

	source_academic_year(frm) {
		_clear_preflight(frm);
	},

	target_academic_year(frm) {
		_clear_preflight(frm);
	},
});

// ---------------------------------------------------------------------------

function _clear_preflight(frm) {
	frm.fields_dict.preflight_html.$wrapper.html(
		`<p class="text-muted small">${__("Clique em «Verificar Pré-condições» para actualizar.")}</p>`
	);
}

async function _run_preflight(frm) {
	if (!frm.doc.source_academic_year || !frm.doc.target_academic_year) {
		frappe.msgprint({
			message: __("Preencha o Ano Actual e o Novo Ano Lectivo antes de verificar."),
			indicator: "orange",
		});
		return;
	}

	const btn = frm.page.get_btn(__("Verificar Pré-condições"));
	if (btn) btn.prop("disabled", true).text(__("A verificar…"));

	const r = await frappe.call({
		method: "escola.escola.doctype.abertura_de_ano_lectivo.abertura_de_ano_lectivo.get_preflight_data",
		args: {
			source_academic_year: frm.doc.source_academic_year,
			target_academic_year: frm.doc.target_academic_year,
		},
	});

	if (btn) btn.prop("disabled", false).text(__("Verificar Pré-condições"));

	if (!r.message) return;
	_render_preflight(frm, r.message);
}

function _render_preflight(frm, d) {
	const ok  = `<span style="color:#2d6a4f;font-weight:700;">✔</span>`;
	const warn = `<span style="color:#e67e00;font-weight:700;">⚠</span>`;
	const err  = `<span style="color:#c0392b;font-weight:700;">✘</span>`;

	// ── Turmas no novo ano ───────────────────────────────────────────
	const groupsOk = d.target_groups.length > 0;
	const groupsIcon = groupsOk ? ok : err;
	let groupsHtml = `<li>${groupsIcon} <b>${__("Turmas no novo ano")}</b>: `;
	if (groupsOk) {
		groupsHtml += `${d.target_groups.length} ${__("turma(s) activa(s)")}`;
	} else {
		groupsHtml += `<span style="color:#c0392b">${__("Nenhuma turma criada — obrigatório antes de submeter.")}</span>`;
	}
	groupsHtml += "</li>";

	// ── Promoções submetidas ─────────────────────────────────────────
	const promoIcon = d.promotions_missing.length === 0 ? ok : warn;
	let promoHtml = `<li>${promoIcon} <b>${__("Promoções de alunos")}</b>: `;
	promoHtml += `${d.promotions_done.length} ${__("submetida(s)")}`;
	if (d.promotions_missing.length) {
		promoHtml += ` · <span style="color:#e67e00">${d.promotions_missing.length} ${__("turma(s) sem promoção")}: `;
		promoHtml += d.promotions_missing.map(g => frappe.utils.escape_html(g.group_name)).join(", ");
		promoHtml += "</span>";
	}
	promoHtml += "</li>";

	// ── Alunos ───────────────────────────────────────────────────────
	const allPromoted = d.students_pending === 0;
	const studentsIcon = allPromoted ? ok : warn;
	let studentsHtml = `<li>${studentsIcon} <b>${__("Alunos do ano actual")}</b>: `;
	studentsHtml += `${d.students_promoted} ${__("já no novo ano")}`;
	if (d.students_pending > 0) {
		studentsHtml += ` · <span style="color:#e67e00">${d.students_pending} ${__("ficam como «Pendente de Renovação» ao submeter")}</span>`;
	}
	studentsHtml += "</li>";

	// ── O que acontece ao submeter ───────────────────────────────────
	const summaryHtml = `
		<div style="background:#f0f4ff;border-radius:6px;padding:10px 14px;margin-top:14px;
		            font-size:12px;color:#374151;border-left:4px solid #4f46e5;">
			<b>${__("Ao submeter este documento:")}</b>
			<ul style="margin:6px 0 0 0;padding-left:16px;">
				<li>${__("Configurações da Escola → Ano Lectivo Actual passa a")} <b>${frappe.utils.escape_html(frm.doc.target_academic_year)}</b></li>
				${d.students_pending > 0
					? `<li>${d.students_pending} ${__("aluno(s) ficam com estado «Pendente de Renovação»")}</li>`
					: `<li>${__("Todos os alunos já estão no novo ano — nenhum estado alterado")}</li>`}
			</ul>
		</div>`;

	const html = `
		<div style="font-size:13px;padding:4px 0;">
			<ul style="list-style:none;padding:0;margin:0;line-height:2.2;">
				${groupsHtml}
				${promoHtml}
				${studentsHtml}
			</ul>
			${summaryHtml}
		</div>`;

	frm.fields_dict.preflight_html.$wrapper.html(html);
}
