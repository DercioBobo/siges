// Copyright (c) 2024, EntreTech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Student Promotion", {
	onload(frm) {
		escola.utils.auto_fill_academic_year(frm);
	},

	refresh(frm) {
		set_queries(frm);

		// If academic_year is set but next_academic_year is missing, try to fill it
		if (frm.doc.academic_year && !frm.doc.next_academic_year) {
			_auto_fill_next_year(frm);
		}

		frm.add_custom_button(__("Gerar Promoção"), () => maybe_generate(frm));

		if (!frm.is_new()) {
			const rows        = frm.doc.promotion_rows || [];
			const can_distrib = rows.length > 0
				&& frm.doc.next_academic_year
				&& frm.doc.status !== "Bloqueado";

			if (can_distrib) {
				const already_done = frm.doc.status === "Finalizado";
				const $btn = frm.add_custom_button(
					already_done
						? __("Redistribuir por Turmas")
						: __("Distribuir por Turmas"),
					() => {
						if (already_done) {
							frappe.confirm(
								__("Esta promoção já foi finalizada. Deseja redistribuir e sobrescrever as atribuições actuais?"),
								() => _show_distribution_modal(frm)
							);
						} else {
							_show_distribution_modal(frm);
						}
					}
				);
				$btn.removeClass("btn-default").addClass("btn-primary");
			}
		}
	},

	academic_year(frm) {
		frm.set_value("class_group", null);
		frm.set_value("next_academic_year", null);
		set_queries(frm);
		if (frm.doc.academic_year) _auto_fill_next_year(frm);
	},

	school_class(frm) {
		frm.set_value("class_group", null);
		set_queries(frm);
	},

	async class_group(frm) {
		set_queries(frm);
		if (!frm.doc.class_group) return;
		const cg = await frappe.db.get_value(
			"Class Group", frm.doc.class_group, ["academic_year", "school_class"]
		);
		if (cg) {
			if (!frm.doc.academic_year && cg.academic_year) {
				// set_value triggers academic_year handler which calls _auto_fill_next_year
				frm.set_value("academic_year", cg.academic_year);
			}
			if (!frm.doc.school_class && cg.school_class)
				frm.set_value("school_class", cg.school_class);
		}
	},

	async next_academic_year(frm) {
		// Validate: next year must be strictly after the origin year
		if (!frm.doc.next_academic_year || !frm.doc.academic_year) return;
		if (frm.doc.next_academic_year === frm.doc.academic_year) {
			frappe.msgprint(__("O Ano Lectivo Seguinte não pode ser igual ao Ano Lectivo de Origem."));
			frm.set_value("next_academic_year", null);
			return;
		}
		const [origin, next] = await Promise.all([
			frappe.db.get_value("Academic Year", frm.doc.academic_year,      "end_date"),
			frappe.db.get_value("Academic Year", frm.doc.next_academic_year, "start_date"),
		]);
		const originEnd  = origin?.end_date   || origin;
		const nextStart  = next?.start_date   || next;
		if (originEnd && nextStart && nextStart <= originEnd) {
			frappe.msgprint(__("O Ano Lectivo Seguinte deve ser posterior ao Ano Lectivo de Origem."));
			frm.set_value("next_academic_year", null);
		}
	},
});

// ---------------------------------------------------------------------------
// Queries
// ---------------------------------------------------------------------------

function set_queries(frm) {
	const f = { is_active: 1 };
	if (frm.doc.academic_year) f.academic_year = frm.doc.academic_year;
	if (frm.doc.school_class)  f.school_class  = frm.doc.school_class;
	frm.set_query("class_group", () => ({ filters: f }));

	// next_academic_year must differ from origin
	frm.set_query("next_academic_year", () => ({
		filters: frm.doc.academic_year
			? { name: ["!=", frm.doc.academic_year] }
			: {},
	}));
}

// ---------------------------------------------------------------------------
// Auto-fill next_academic_year
// ---------------------------------------------------------------------------

async function _auto_fill_next_year(frm) {
	if (!frm.doc.academic_year) return;
	// Don't overwrite a value the user already chose
	if (frm.doc.next_academic_year) return;

	const r = await frappe.call({
		method: "escola.escola.doctype.student_promotion.student_promotion.get_or_suggest_next_academic_year",
		args:   { academic_year: frm.doc.academic_year },
	});

	if (!r.message) return;
	const d = r.message;

	if (d.found) {
		frm.set_value("next_academic_year", d.name);
		return;
	}

	if (d.error) return;  // e.g. no_end_date — silently skip

	// Not found — ask the user if they want to create it
	const name    = d.suggested_name || "";
	const start   = frappe.datetime.str_to_user(d.start_date);
	const end_d   = frappe.datetime.str_to_user(d.end_date);

	frappe.confirm(
		__("Não existe Ano Lectivo seguinte a <b>{0}</b>.<br><br>"
		 + "Deseja criar <b>{1}</b> ({2} → {3})?",
		   [frm.doc.academic_year, name, start, end_d]),
		async () => {
			// Create the Academic Year
			const result = await frappe.call({
				method: "frappe.client.insert",
				args: {
					doc: {
						doctype:             "Academic Year",
						academic_year_name:  name,
						start_date:          d.start_date,
						end_date:            d.end_date,
					},
				},
			});
			if (result.message) {
				frm.set_value("next_academic_year", result.message.name);
				frappe.show_alert({
					message: __("Ano Lectivo <b>{0}</b> criado.", [result.message.name]),
					indicator: "green",
				}, 4);
			}
		}
	);
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
		args:   { doc_name: frm.doc.name },
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

	const approved  = msg.filter(r => r.decision === "Promovido").length;
	const concluded = msg.filter(r => r.decision === "Concluído").length;
	const retained  = msg.filter(r => r.decision === "Retido").length;
	frappe.show_alert({
		message: __("{0} aprovado(s) · {1} concluído(s) · {2} reprovado(s). Guarde para confirmar.",
			[approved, concluded, retained]),
		indicator: "green",
	});
}

// ---------------------------------------------------------------------------
// Distribution modal — styles (injected once)
// ---------------------------------------------------------------------------

function _inject_spm_styles() {
	if (document.getElementById("escola-spm-styles")) return;
	const s = document.createElement("style");
	s.id = "escola-spm-styles";
	s.textContent = `
/* ── Layout ─────────────────────────────────────── */
.spm-section { padding: 20px 24px; }
.spm-section + .spm-section { border-top: 1px solid var(--border-color); }

.spm-section-head { display: flex; align-items: center; gap: 10px; margin-bottom: 14px; }
.spm-section-title { font-size: 14px; font-weight: 700; }
.spm-dest {
	font-size: 11px; color: var(--text-muted); padding: 2px 9px;
	background: var(--subtle-fg); border-radius: 12px; white-space: nowrap;
}
.spm-concl-note {
	font-size: 12px; color: var(--text-muted); background: var(--subtle-fg);
	padding: 8px 12px; border-radius: 8px; margin-bottom: 10px;
}
.spm-assigned-note {
	font-size: 12px; color: #065f46; background: #d1fae5;
	padding: 8px 12px; border-radius: 8px; margin-bottom: 10px;
	border: 1px solid #6ee7b7;
}
.spm-empty-note { font-size: 12px; color: var(--text-muted); padding: 8px 0; }

/* ── Capacity bars ───────────────────────────────── */
.spm-groups { margin-bottom: 14px; }
.spm-group-row { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.spm-group-name { font-size: 12px; font-weight: 600; min-width: 90px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.spm-bar-wrap { flex: 1; height: 7px; background: var(--border-color); border-radius: 4px; overflow: hidden; min-width: 60px; }
.spm-bar-fill { height: 100%; border-radius: 4px; transition: width .3s; }
.spm-bar-cap { font-size: 11px; color: var(--text-muted); min-width: 42px; text-align: right; }
.spm-bar-free { font-size: 11px; min-width: 70px; }
.spm-no-groups { font-size: 12px; color: var(--text-muted); font-style: italic; margin-bottom: 14px; }

/* ── Options ─────────────────────────────────────── */
.spm-opts-label {
	font-size: 10px; font-weight: 700; text-transform: uppercase;
	letter-spacing: .7px; color: var(--text-muted); margin-bottom: 8px;
}
.spm-option {
	display: flex; align-items: flex-start; gap: 8px;
	padding: 8px 10px; border-radius: 8px; cursor: pointer;
	border: 1.5px solid transparent; margin-bottom: 5px;
	transition: border-color .15s, background .15s;
}
.spm-option:hover { background: var(--subtle-fg); }
.spm-option.selected { border-color: var(--primary); background: color-mix(in srgb, var(--primary) 8%, transparent); }
.spm-option input[type=radio] { margin-top: 2px; flex-shrink: 0; accent-color: var(--primary); }
.spm-star { color: #f59e0b; font-size: 13px; width: 14px; flex-shrink: 0; line-height: 1.5; }
.spm-opt-text { font-size: 13px; font-weight: 500; flex: 1; line-height: 1.4; }
.spm-warn {
	font-size: 10px; font-weight: 600; padding: 2px 7px; border-radius: 10px;
	flex-shrink: 0; align-self: center; white-space: nowrap;
}
.spm-warn.overfill       { background: #fef3c7; color: #b45309; }
.spm-warn.not_recommended { background: #f3f4f6; color: #6b7280; }

/* ── Plan area ───────────────────────────────────── */
.spm-plan {
	margin-top: 10px; padding: 12px 14px;
	background: var(--subtle-fg); border-radius: 8px;
	border: 1px solid var(--border-color);
}
.spm-plan-label {
	font-size: 10px; font-weight: 700; text-transform: uppercase;
	letter-spacing: .7px; color: var(--text-muted); margin-bottom: 8px;
}
.spm-plan-row { display: flex; align-items: center; gap: 8px; margin-bottom: 7px; }
.spm-plan-row:last-child { margin-bottom: 0; }
.spm-plan-name { font-size: 13px; font-weight: 600; }
.spm-plan-arrow { color: var(--text-muted); flex-shrink: 0; }
.spm-plan-count { font-size: 13px; color: var(--text-muted); flex-shrink: 0; }
.spm-plan-result { font-size: 12px; color: var(--text-muted); }
.spm-plan-result.over { color: #dc2626; font-weight: 700; }
.spm-new-badge {
	font-size: 10px; font-weight: 700; background: #ede9fe; color: #6d28d9;
	padding: 2px 7px; border-radius: 10px; flex-shrink: 0;
}
.spm-name-inp {
	flex: 1; padding: 5px 9px; border: 1.5px solid var(--border-color);
	border-radius: 6px; font-size: 12px; background: var(--fg-color);
	color: var(--text-color); outline: none; transition: border-color .15s;
	min-width: 0;
}
.spm-name-inp:focus { border-color: var(--primary); }
.spm-cap-label { font-size: 11px; color: var(--text-muted); flex-shrink: 0; }
.spm-cap-inp {
	width: 72px; padding: 5px 9px; border: 1.5px solid var(--border-color);
	border-radius: 6px; font-size: 12px; background: var(--fg-color);
	color: var(--text-color); outline: none; transition: border-color .15s;
}
.spm-cap-inp:focus { border-color: var(--primary); }
	`;
	document.head.appendChild(s);
}

// ---------------------------------------------------------------------------
// Distribution modal — entry point
// ---------------------------------------------------------------------------

async function _show_distribution_modal(frm) {
	if (!frm.doc.next_academic_year) {
		frappe.msgprint(__("Defina o <b>Ano Lectivo Seguinte</b> antes de distribuir por turmas."));
		return;
	}

	const r = await frappe.call({
		method: "escola.escola.doctype.student_promotion.student_promotion.get_promotion_turma_options",
		args:   { promotion_name: frm.doc.name },
		freeze: true,
		freeze_message: __("A calcular opções…"),
	});

	if (!r.message) return;
	const data = r.message;

	const total_pending = (data.aprovados_count || 0) + (data.reprovados_count || 0);
	const total_assigned = (data.already_assigned_aprovados || 0) + (data.already_assigned_reprovados || 0);

	if (!total_pending && !total_assigned) {
		frappe.msgprint(__("Não há alunos Aprovados nem Reprovados para distribuir."));
		return;
	}
	if (!total_pending && total_assigned) {
		frappe.msgprint({
			title: __("Todos os alunos já alocados"),
			message: __("Todos os {0} aluno(s) já foram alocados a turmas no ano lectivo <b>{1}</b>.",
				[total_assigned, data.next_academic_year]),
			indicator: "green",
		});
		return;
	}

	_inject_spm_styles();

	// ── State ────────────────────────────────────────────────────────────────
	const state = {
		apr_idx: Math.max(0, (data.aprovados_options || []).findIndex(o => o.recommended)),
		ret_idx: Math.max(0, (data.reprovados_options || []).findIndex(o => o.recommended)),
		new_vals: {},  // temp_id → { name, capacity }
	};

	// Ensure recommended defaults to index 0 when no option is flagged recommended
	if (state.apr_idx < 0) state.apr_idx = 0;
	if (state.ret_idx < 0) state.ret_idx = 0;

	// Pre-populate new_vals from every option's new_groups
	[...(data.aprovados_options || []), ...(data.reprovados_options || [])].forEach(opt => {
		(opt.new_groups || []).forEach(ng => {
			if (!state.new_vals[ng.temp_id]) {
				state.new_vals[ng.temp_id] = {
					name:     ng.suggested_name || "",
					capacity: ng.capacity       || 0,
				};
			}
		});
	});

	// ── Dialog ───────────────────────────────────────────────────────────────
	const d = new frappe.ui.Dialog({
		title: __("Distribuir por Turmas · {0}", [frm.doc.name]),
		size:  "large",
	});
	d.$body.css("padding", "0");

	function render() {
		const html = [];

		// Aprovados section
		if (data.aprovados_count > 0 || data.already_assigned_aprovados > 0) {
			html.push(_render_spm_section(
				"apr",
				__("Aprovados — passam para {0}", [data.next_school_class || __("próxima classe")]),
				data.aprovados_count,
				data.next_school_class, data.next_academic_year,
				data.target_groups, data.aprovados_options, state.apr_idx, state,
				data.already_assigned_aprovados || 0
			));
		}

		// Concluídos info
		if (data.concluidos_count > 0) {
			html.push(`
				<div class="spm-section">
					<div class="spm-section-head">
						<span class="spm-section-title">${__("Concluídos")} (${data.concluidos_count})</span>
					</div>
					<div class="spm-concl-note">
						✓ ${__("Estes alunos concluíram o último nível — nenhuma inscrição necessária.")}
					</div>
				</div>`
			);
		}

		// Reprovados section
		if (data.reprovados_count > 0 || data.already_assigned_reprovados > 0) {
			if (html.length) html.push(""); // separator handled by CSS border-top
			html.push(_render_spm_section(
				"ret",
				__("Reprovados / Repetentes — ficam em {0}", [data.school_class || __("mesma classe")]),
				data.reprovados_count,
				data.school_class, data.next_academic_year,
				data.retained_groups, data.reprovados_options, state.ret_idx, state,
				data.already_assigned_reprovados || 0
			));
		}

		d.$body.html(`<div>${html.join("")}</div>`);
		_bind_spm_events(d.$body, state, data, render);
	}

	render();

	d.set_primary_action(__("Confirmar e Criar Inscrições"), async () => {
		const plan = _build_spm_plan(state, data);
		if (!_validate_spm_plan(plan)) return;

		const result = await frappe.call({
			method: "escola.escola.doctype.student_promotion.student_promotion.execute_promotion_plan",
			args:   { promotion_name: frm.doc.name, plan: JSON.stringify(plan) },
			freeze: true,
			freeze_message: __("A criar turmas e inscrições…"),
		});

		d.hide();
		if (!result.message) return;
		const m = result.message;

		const parts = [__("<b>{0}</b> aluno(s) alocado(s) às turmas", [m.created])];
		if (m.skipped)
			parts.push(__("<b>{0}</b> já alocado(s) anteriormente — ignorados", [m.skipped]));
		if (m.created_groups && m.created_groups.length)
			parts.push(__("<b>{0}</b> turma(s) nova(s) criada(s): {1}",
				[m.created_groups.length, m.created_groups.join(", ")]));

		let msg = parts.join("<br>");
		if (m.errors && m.errors.length)
			msg += "<br><br><b>" + __("Avisos:") + "</b><br>" + m.errors.join("<br>");

		frappe.msgprint({
			title:     __("Alocação Concluída"),
			message:   msg,
			indicator: m.errors && m.errors.length ? "orange" : "green",
		});
		frm.reload_doc();
	});

	d.show();
}

// ---------------------------------------------------------------------------
// Distribution modal — section renderer
// ---------------------------------------------------------------------------

function _render_spm_section(prefix, title, count, school_class_name, academic_year, groups, options, selected_idx, state, already_assigned) {
	const dest = academic_year || "";

	// Already-assigned note (shown when redistribuindo)
	const assigned_note = already_assigned > 0
		? `<div class="spm-assigned-note">
			✓ ${__("{0} aluno(s) já alocado(s) anteriormente — serão ignorados nesta distribuição.", [already_assigned])}
		   </div>`
		: "";

	// No-remaining note
	if (count === 0 && already_assigned > 0) {
		return `
		<div class="spm-section">
			<div class="spm-section-head">
				<span class="spm-section-title">${title}</span>
				${dest ? `<span class="spm-dest">${frappe.utils.escape_html(dest)}</span>` : ""}
			</div>
			${assigned_note}
		</div>`;
	}

	// Capacity bars
	const groups_html = groups && groups.length
		? `<div class="spm-groups">${groups.map(g => {
			const used  = g.student_count || 0;
			const max   = g.max_students  || 0;
			const free  = max ? Math.max(0, max - used) : null;
			const pct   = max ? Math.min(100, (used / max) * 100) : 0;
			const color = pct >= 100 ? "#ef4444" : pct >= 80 ? "#f59e0b" : "#3b82f6";
			return `
			<div class="spm-group-row">
				<span class="spm-group-name" title="${frappe.utils.escape_html(g.group_name)}">${frappe.utils.escape_html(g.group_name)}</span>
				${max ? `
					<div class="spm-bar-wrap"><div class="spm-bar-fill" style="width:${pct}%;background:${color};"></div></div>
					<span class="spm-bar-cap">${used}/${max}</span>
					<span class="spm-bar-free" style="color:${free === 0 ? "#ef4444" : "var(--text-muted)"};">
						${free === 0 ? __("Cheia") : `+${free} ${__("vagas")}`}
					</span>
				` : `<span class="spm-bar-free" style="color:var(--text-muted);">${used} ${__("alunos")} · ${__("sem limite")}</span>`}
			</div>`;
		}).join("")}</div>`
		: `<div class="spm-no-groups">${__("Nenhuma turma existente para {0}", [school_class_name || __("esta classe")])}</div>`;

	// Radio options
	const options_html = (options || []).map((opt, i) => {
		const sel      = i === selected_idx;
		const warn_cls = opt.warning === "overfill" ? "overfill" : opt.warning ? "not_recommended" : "";
		const warn_lbl = opt.warning === "overfill"
			? __("⚠ excede capacidade")
			: opt.warning === "not_recommended"
				? __("não recomendado")
				: "";
		return `
		<label class="spm-option ${sel ? "selected" : ""}">
			<input type="radio" name="${prefix}-opt" value="${i}" ${sel ? "checked" : ""}>
			<span class="spm-star">${opt.recommended ? "★" : "&nbsp;"}</span>
			<span class="spm-opt-text">${frappe.utils.escape_html(opt.label)}</span>
			${warn_lbl ? `<span class="spm-warn ${warn_cls}">${warn_lbl}</span>` : ""}
		</label>`;
	}).join("");

	const selected_opt = (options || [])[selected_idx];
	const plan_html    = selected_opt ? _render_spm_plan(prefix, selected_opt, state) : "";

	return `
	<div class="spm-section">
		<div class="spm-section-head">
			<span class="spm-section-title">${title} (${count} ${__("por alocar")})</span>
			${dest ? `<span class="spm-dest">${frappe.utils.escape_html(dest)}</span>` : ""}
		</div>
		${assigned_note}
		${groups_html}
		<div class="spm-opts-label">${__("Como distribuir os {0} alunos:", [count])}</div>
		<div id="${prefix}-options">${options_html}</div>
		<div id="${prefix}-plan">${plan_html}</div>
	</div>`;
}

// ---------------------------------------------------------------------------
// Distribution modal — plan area renderer
// ---------------------------------------------------------------------------

function _render_spm_plan(prefix, option, state) {
	if (!option) return "";
	const rows = [];

	// Existing buckets
	for (const b of (option.buckets || [])) {
		const over = b.max && b.after > b.max;
		rows.push(`
		<div class="spm-plan-row">
			<span class="spm-plan-name">${frappe.utils.escape_html(b.group_name)}</span>
			<span class="spm-plan-arrow">→</span>
			<span class="spm-plan-count">${b.count} ${__("alunos")}</span>
			${b.max ? `<span class="spm-plan-result ${over ? "over" : ""}">(${b.after}/${b.max}${over ? " ⚠" : ""})</span>` : ""}
		</div>`);
	}

	// New group buckets — editable name + capacity
	for (const ng of (option.new_groups || [])) {
		const v = state.new_vals[ng.temp_id] || { name: ng.suggested_name, capacity: ng.capacity };
		rows.push(`
		<div class="spm-plan-row" style="flex-wrap:wrap;gap:6px 8px;">
			<span class="spm-new-badge">${__("Nova")}</span>
			<div style="display:flex;flex-direction:column;flex:1;min-width:120px;gap:2px;">
				<input class="spm-name-inp" type="text"
					value="${frappe.utils.escape_html(v.name || "")}"
					placeholder="${__("Nome da turma")}"
					data-field="name" data-tid="${ng.temp_id}">
				<span style="font-size:10px;color:var(--text-muted);">
					${__("Formato:")} <code style="font-size:10px;">{Classe} {letra}-{AA}</code>
					&nbsp;·&nbsp; ${__("Ex:")} <b>${frappe.utils.escape_html(ng.suggested_name)}</b>
				</span>
			</div>
			<span class="spm-plan-arrow">→</span>
			<span class="spm-plan-count">${ng.count} ${__("alunos")}</span>
			<span class="spm-cap-label">${__("Limite:")}</span>
			<input class="spm-cap-inp" type="text" inputmode="numeric" pattern="[0-9]*"
				value="${v.capacity > 0 ? v.capacity : ""}"
				placeholder="${__("Ilimitado")}"
				data-field="cap" data-tid="${ng.temp_id}">
		</div>`);
	}

	if (!rows.length) return "";

	return `
	<div class="spm-plan">
		<div class="spm-plan-label">${__("Plano de distribuição:")}</div>
		${rows.join("")}
	</div>`;
}

// ---------------------------------------------------------------------------
// Distribution modal — event binding
// ---------------------------------------------------------------------------

function _bind_spm_events($body, state, data, render) {
	// Radio selection — full re-render of the section plan area
	$body.find("input[type=radio]").on("change", function () {
		const name = $(this).attr("name");
		const idx  = parseInt($(this).val());
		if (name === "apr-opt") state.apr_idx = idx;
		else if (name === "ret-opt") state.ret_idx = idx;
		render();
	});

	// New group name / capacity — update state without full re-render
	$body.on("input", ".spm-name-inp, .spm-cap-inp", function () {
		const tid   = $(this).data("tid");
		const field = $(this).data("field");
		if (!state.new_vals[tid]) state.new_vals[tid] = { name: "", capacity: 0 };
		if (field === "name") state.new_vals[tid].name     = $(this).val();
		if (field === "cap")  state.new_vals[tid].capacity = parseInt($(this).val()) || 0;
	});
}

// ---------------------------------------------------------------------------
// Distribution modal — plan builder + validator
// ---------------------------------------------------------------------------

function _build_spm_plan(state, data) {
	function resolve(options, idx, new_vals) {
		const opt = (options || [])[idx];
		if (!opt) return [];
		const result = [];
		for (const b of (opt.buckets || [])) {
			result.push({ type: "existing", class_group: b.class_group, count: b.count });
		}
		for (const ng of (opt.new_groups || [])) {
			const v = new_vals[ng.temp_id] || { name: ng.suggested_name, capacity: ng.capacity };
			result.push({
				type:          "new",
				temp_id:       ng.temp_id,
				name:          v.name || ng.suggested_name,
				school_class:  ng.school_class,
				academic_year: ng.academic_year,
				count:         ng.count,
				capacity:      v.capacity !== undefined ? v.capacity : ng.capacity,
			});
		}
		return result;
	}

	return {
		aprovados:  resolve(data.aprovados_options,  state.apr_idx, state.new_vals),
		reprovados: resolve(data.reprovados_options, state.ret_idx, state.new_vals),
	};
}

function _validate_spm_plan(plan) {
	for (const b of [...(plan.aprovados || []), ...(plan.reprovados || [])]) {
		if (b.type === "new" && !(b.name || "").trim()) {
			frappe.msgprint(__("Por favor, defina o nome para todas as novas turmas."));
			return false;
		}
	}
	return true;
}
