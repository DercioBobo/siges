// Copyright (c) 2024, EntreTech and contributors
// For license information, please see license.txt

const _FINANCIAL_COLORS = {
	"Regular":           "green",
	"Em Dívida":         "yellow",
	"Em Dívida Crítica": "orange",
	"Suspenso":          "red",
};

const _ALERT_MESSAGES = {
	1: "Pagamento em atraso",
	2: "Multa significativa aplicada",
	3: "Risco de suspensão",
	4: "Aluno elegível para suspensão",
};


frappe.ui.form.on("Student", {
	refresh(frm) {
		if (!frm.is_new()) {
			_set_financial_indicator(frm);
			_load_financial_summary(frm);
			_load_academic_history(frm);
			_load_renewal_status(frm);
			_load_documents(frm);

			const $btn = frm.add_custom_button(__("Acções"), () => _show_actions_modal(frm));
			$btn.removeClass("btn-default").addClass("btn-primary");
		}
	},

	first_name(frm)    { update_full_name(frm); },
	last_name(frm)     { update_full_name(frm); },
	date_of_birth(frm) { update_age(frm); },
});

// ---------------------------------------------------------------------------
// Actions modal (single toolbar button → modal with card grid)
// ---------------------------------------------------------------------------

function _inject_student_styles() {
	if (document.getElementById("escola-student-styles")) return;
	const s = document.createElement("style");
	s.id = "escola-student-styles";
	s.textContent = `
/* ── Actions modal ───────────────────────────── */
.sam-section { margin-bottom: 20px; }
.sam-label {
	font-size: 10px; font-weight: 700; text-transform: uppercase;
	letter-spacing: .8px; color: var(--text-muted); margin-bottom: 10px;
}
.sam-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 10px; }
.sam-card {
	display: flex; flex-direction: column; align-items: center; justify-content: center;
	gap: 8px; padding: 16px 10px; border-radius: 10px;
	border: 1.5px solid transparent; cursor: pointer;
	transition: transform .13s, box-shadow .13s, filter .13s;
	text-align: center; font-family: var(--font-stack);
	min-height: 80px;
}
.sam-card:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,.12); filter: brightness(.96); }
.sam-card:active { transform: translateY(0); box-shadow: none; }
.sam-ico { font-size: 22px; line-height: 1; }
.sam-lbl { font-size: 12px; font-weight: 600; line-height: 1.3; }

/* ── Renewal history panel ───────────────────── */
.srn-header {
	display: flex; align-items: center; justify-content: space-between;
	margin-bottom: 6px;
}
.srn-title { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: .8px; color: var(--text-muted); }
.srn-all-link { font-size: 11px; color: #6366f1; text-decoration: none; }
.srn-all-link:hover { text-decoration: underline; }
.srn-row {
	display: flex; flex-direction: column; gap: 3px;
	padding: 7px 10px; border-radius: 7px; margin-bottom: 5px;
	border: 1px solid var(--border-color); background: var(--fg-color);
	font-size: 12px;
}
.srn-row-top    { display: flex; align-items: center; justify-content: space-between; gap: 6px; }
.srn-row-bottom { display: flex; align-items: center; gap: 6px; }
.srn-years { font-weight: 700; font-size: 13px; }
.srn-date  { color: var(--text-muted); font-size: 11px; }
.srn-badge {
	font-size: 11px; font-weight: 600; padding: 2px 8px;
	border-radius: 12px; white-space: nowrap;
}
.srn-badge.confirmed { background: #d1fae5; color: #065f46; }
.srn-badge.draft     { background: #fef3c7; color: #92400e; }
.srn-ver { font-size: 11px; font-weight: 600; color: #6366f1; cursor: pointer; background: none; border: none; padding: 0; white-space: nowrap; }
.srn-ver:hover { text-decoration: underline; }
.srn-pending {
	display: flex; align-items: center; gap: 8px;
	padding: 8px 10px; border-radius: 7px; margin-bottom: 5px;
	background: #fef3c7; border: 1px solid #fcd34d;
	font-size: 12px; font-weight: 500; color: #92400e;
}
.srn-pending-btn {
	margin-left: auto; font-size: 11px; font-weight: 600; padding: 3px 9px;
	border-radius: 6px; background: #d97706; color: #fff;
	cursor: pointer; border: none; outline: none; white-space: nowrap;
}
.srn-empty { font-size: 12px; color: var(--text-muted); padding: 4px 0; }

/* ── Forecast modal ──────────────────────────── */
.sfrc-summary { display:grid; grid-template-columns:repeat(auto-fill,minmax(140px,1fr)); gap:12px; margin-bottom:20px; }
.sfrc-stat { border-radius:10px; padding:14px 16px; }
.sfrc-stat-label { font-size:10px; font-weight:700; text-transform:uppercase; letter-spacing:.07em; opacity:.75; margin-bottom:6px; }
.sfrc-stat-val { font-size:20px; font-weight:800; line-height:1; }
.sfrc-badge { display:inline-flex; align-items:center; gap:5px; font-size:11px; font-weight:700; padding:2px 9px; border-radius:12px; white-space:nowrap; }
.sfrc-dot { width:7px; height:7px; border-radius:50%; flex-shrink:0; }

/* ── Invoice modal ───────────────────────────── */
.sinv-summary { display:grid; grid-template-columns:repeat(3,1fr); gap:12px; margin-bottom:20px; }
.sinv-card { border-radius:10px; padding:14px 16px; }
.sinv-card-label { font-size:10px; font-weight:700; text-transform:uppercase; letter-spacing:.07em; opacity:.75; margin-bottom:6px; }
.sinv-card-val { font-size:22px; font-weight:800; line-height:1; }
.sinv-table { width:100%; border-collapse:collapse; font-size:13px; }
.sinv-table thead tr { background:#f1f5f9; }
.sinv-table th { padding:8px 12px; text-align:left; font-size:10px; font-weight:700; color:#64748b; text-transform:uppercase; letter-spacing:.06em; border-bottom:2px solid #e2e8f0; white-space:nowrap; }
.sinv-table th.num { text-align:right; }
.sinv-table td { padding:9px 12px; border-bottom:1px solid #f1f5f9; vertical-align:middle; }
.sinv-table td.num { text-align:right; font-variant-numeric:tabular-nums; }
.sinv-table tr:last-child td { border-bottom:none; }
.sinv-table tr:hover td { background:#f8fafc; }
.sinv-badge { display:inline-block; font-size:11px; font-weight:700; padding:2px 9px; border-radius:12px; white-space:nowrap; }
.sinv-link { color:#2563eb; text-decoration:none; font-weight:600; }
.sinv-link:hover { text-decoration:underline; }
.sinv-empty { text-align:center; padding:40px; color:#9ca3af; font-size:14px; }
.sinv-footer { margin-top:14px; text-align:right; }
.sinv-footer a { font-size:12px; color:#6366f1; text-decoration:none; }
.sinv-footer a:hover { text-decoration:underline; }

/* ── Timeline modal ──────────────────────────── */
.stl-item { display: flex; gap: 16px; position: relative; }
.stl-item:not(:last-child) { padding-bottom: 24px; }
.stl-spine { display: flex; flex-direction: column; align-items: center; flex-shrink: 0; width: 20px; }
.stl-dot {
	width: 14px; height: 14px; border-radius: 50%; margin-top: 16px; z-index: 1;
	border: 2.5px solid white; flex-shrink: 0;
}
.stl-line { width: 2px; flex: 1; background: var(--border-color); margin-top: 5px; }
.stl-card {
	flex: 1; border: 1px solid var(--border-color); border-radius: 10px;
	overflow: hidden; margin-top: 8px; background: var(--fg-color);
}
.stl-head {
	padding: 10px 14px; display: flex; align-items: center;
	justify-content: space-between; border-bottom: 1px solid var(--border-color);
}
.stl-year { font-weight: 700; font-size: 15px; }
.stl-status-badge { font-size: 11px; font-weight: 600; padding: 2px 9px; border-radius: 12px; margin-left: 8px; }
.stl-result { font-weight: 700; font-size: 13px; }
.stl-body { padding: 10px 14px; display: flex; gap: 22px; flex-wrap: wrap; }
.stl-stat-label { font-size: 10px; color: var(--text-muted); text-transform: uppercase; letter-spacing: .06em; margin-bottom: 2px; }
.stl-stat-val { font-size: 13px; font-weight: 500; }
.stl-foot { padding: 7px 14px; border-top: 1px solid var(--border-color); background: var(--subtle-fg); display: flex; gap: 16px; flex-wrap: wrap; }
.stl-foot a { font-size: 12px; color: #6366f1; text-decoration: none; }
.stl-foot a:hover { text-decoration: underline; }
.stl-empty { text-align: center; padding: 40px 16px; color: var(--text-muted); font-size: 13px; }
	`;
	document.head.appendChild(s);
}

function _show_actions_modal(frm) {
	_inject_student_styles();

	const status      = frm.doc.current_status;
	const isActive    = !status || status === "Activo";
	const isInactive  = status === "Transferido" || status === "Desistente";
	const isConcluded = status === "Concluiu";

	// Show renewal card only when in active renewal period and student can still renew
	const inRenewalPeriod = !isConcluded && frm._renewal_status && frm._renewal_status.in_period;
	const alreadyRenewed  = inRenewalPeriod && frm._renewal_status.renewal;

	const hasTurma = !!frm.doc.current_class_group;

	const ver = [
		{ id: "boletins",    ico: "📋", label: __("Boletins"),           color: "#4f46e5", bg: "#eef2ff" },
		{ id: "resultados",  ico: "📊", label: __("Resultados"),          color: "#0369a1", bg: "#e0f2fe" },
		{ id: "facturas",    ico: "🧾", label: __("Facturas"),            color: "#059669", bg: "#d1fae5" },
		{ id: "previsao",    ico: "📅", label: __("Previsão Financeira"), color: "#0891b2", bg: "#ecfeff" },
		{ id: "servicos",    ico: "🔧", label: __("Serviços Extras"),     color: "#0f766e", bg: "#f0fdfa" },
		{ id: "historial",   ico: "🕐", label: __("Ver Historial"),       color: "#7c3aed", bg: "#f5f3ff" },
		...(hasTurma ? [
			{ id: "ver-turma",   ico: "👥", label: __("Ver Turma"),   color: "#0f766e", bg: "#f0fdfa" },
			{ id: "ver-horario", ico: "📆", label: __("Ver Horário"), color: "#7c3aed", bg: "#fdf4ff" },
		] : []),
		...(inRenewalPeriod ? [{
			id:    alreadyRenewed ? "ver-renovacao" : "nova-renovacao",
			ico:   alreadyRenewed ? "✓" : "🔄",
			label: alreadyRenewed ? __("Ver Renovação") : __("Renovar Matrícula"),
			color: alreadyRenewed ? "#059669" : "#b45309",
			bg:    alreadyRenewed ? "#d1fae5"  : "#fffbeb",
		}] : []),
	];

	const acoes = [
		{ id: "atribuir-turma",    ico: "＋", label: __("Atribuir Turma"),               color: "#1d4ed8", bg: "#eff6ff", show: !isConcluded },
		{ id: "troca-turma",       ico: "⇄",  label: __("Trocar de Turma"),              color: "#6d28d9", bg: "#f5f3ff", show: isActive   },
		{ id: "transferencia",     ico: "✈",  label: __("Registar Transferência"),       color: "#b45309", bg: "#fffbeb", show: isActive   },
		{ id: "desistencia",       ico: "✕",  label: __("Registar Desistência"),         color: "#dc2626", bg: "#fef2f2", show: isActive   },
		{ id: "estado-financeiro", ico: "↻",  label: __("Actualizar Estado Financeiro"), color: "#374151", bg: "#f3f4f6", show: true       },
		{ id: "reactivar",         ico: "↺",  label: __("Reactivar Aluno"),              color: "#166534", bg: "#f0fdf4", show: isInactive },
	].filter(b => b.show);

	const cards = (items) => items.map(b => `
		<div class="sam-card" data-action="${b.id}"
		     style="background:${b.bg};border-color:${b.color}22;">
			<span class="sam-ico">${b.ico}</span>
			<span class="sam-lbl" style="color:${b.color};">${b.label}</span>
		</div>`
	).join("");

	const d = new frappe.ui.Dialog({
		title: frm.doc.full_name,
		size:  "large",
	});

	d.$body.css("padding", "20px 24px 8px");
	d.$body.html(`
		<div class="sam-section">
			<div class="sam-label">${__("Ver")}</div>
			<div class="sam-grid">${cards(ver)}</div>
		</div>
		<div class="sam-section">
			<div class="sam-label">${__("Acções")}</div>
			<div class="sam-grid">${cards(acoes)}</div>
		</div>
	`);

	d.$body.find("[data-action]").on("click", function () {
		const a = $(this).data("action");
		d.hide();
		switch (a) {
			case "boletins":
				frappe.route_options = { student: frm.doc.name };
				frappe.set_route("boletim-aluno");
				break;
			case "resultados":        _show_student_results_modal(frm); break;
			case "ver-turma":
				frappe.set_route("Form", "Class Group", frm.doc.current_class_group);
				break;
			case "ver-horario":
				frappe.route_options = { class_group: frm.doc.current_class_group };
				frappe.set_route("timetable-view");
				break;
			case "facturas":          _show_invoices_modal(frm); break;
			case "previsao":          _show_forecast_modal(frm); break;
			case "servicos":          _show_services_modal(frm); break;
			case "historial":         _show_timeline_modal(frm); break;
			case "atribuir-turma":    _assign_class_group_dialog(frm); break;
			case "troca-turma":       frappe.new_doc("Troca De Turma", { student: frm.doc.name }); break;
			case "transferencia":     frappe.new_doc("Student Transfer", { student: frm.doc.name }); break;
			case "desistencia":       _register_withdrawal_dialog(frm); break;
			case "estado-financeiro": _update_financial_status(frm); break;
			case "reactivar":         reactivate_dialog(frm); break;
			case "nova-renovacao":
				if (frm._renewal_status) _open_new_renewal(frm, frm._renewal_status);
				break;
			case "ver-renovacao":
				frappe.set_route("List", "Renovacao De Matricula", { student: frm.doc.name });
				break;
		}
	});

	d.$wrapper.find(".btn-modal-primary").hide();
	d.set_secondary_action_label(__("Fechar"));
	d.set_secondary_action(() => d.hide());
	d.show();
}

// ---------------------------------------------------------------------------
// Assign class group dialog
// ---------------------------------------------------------------------------

async function _assign_class_group_dialog(frm) {
	const [ay_r] = await Promise.all([
		frappe.db.get_single_value("School Settings", "current_academic_year"),
	]);
	const default_year  = ay_r || null;
	const default_class = frm.doc.current_school_class || null;

	const d = new frappe.ui.Dialog({
		title: __("Atribuir Turma · {0}", [frm.doc.full_name]),
		fields: [
			{
				fieldname: "academic_year",
				fieldtype: "Link",
				options:   "Academic Year",
				label:     __("Ano Lectivo"),
				reqd:      1,
				default:   default_year,
				onchange() {
					d.set_value("school_class", null);
					d.set_value("class_group",  null);
				},
			},
			{
				fieldname: "school_class",
				fieldtype: "Link",
				options:   "School Class",
				label:     __("Classe"),
				default:   default_class,
				get_query: () => ({ filters: { is_active: 1 } }),
				onchange() {
					d.set_value("class_group", null);
					d.fields_dict.class_group.get_query = () => ({ filters: _cg_filters(d) });
				},
			},
			{
				fieldname: "class_group",
				fieldtype: "Link",
				options:   "Class Group",
				label:     __("Turma"),
				reqd:      1,
				get_query: () => ({ filters: _cg_filters(d) }),
				description: __("Seleccione a turma de destino."),
			},
			{
				fieldname:  "assignment_date",
				fieldtype:  "Date",
				label:      __("Data de Atribuição"),
				default:    frappe.datetime.get_today(),
				reqd:       1,
			},
			{
				fieldname: "notes",
				fieldtype: "Small Text",
				label:     __("Observações"),
			},
		],
		primary_action_label: __("Atribuir"),
		primary_action(values) {
			frappe.call({
				method: "frappe.client.insert",
				args: {
					doc: {
						doctype:         "Student Group Assignment",
						student:         frm.doc.name,
						academic_year:   values.academic_year,
						school_class:    values.school_class || null,
						class_group:     values.class_group,
						assignment_date: values.assignment_date,
						status:          "Activa",
						notes:           values.notes || "",
					},
				},
				callback(r) {
					if (r.exc) return;
					d.hide();
					frappe.show_alert({ message: __("Aluno atribuído à turma com sucesso."), indicator: "green" });
					frm.reload_doc();
				},
			});
		},
	});
	d.show();
}

function _cg_filters(d) {
	const f = { is_active: 1 };
	const ay = d.get_value("academic_year");
	const sc = d.get_value("school_class");
	if (ay) f.academic_year = ay;
	if (sc) f.school_class  = sc;
	return f;
}

// ---------------------------------------------------------------------------
// Update financial status
// ---------------------------------------------------------------------------

function _update_financial_status(frm) {
	frappe.call({
		method:         "escola.escola.doctype.billing_cycle.penalty.update_student_financial_status",
		args:           { student_name: frm.doc.name },
		freeze:         true,
		freeze_message: __("A calcular estado financeiro..."),
		callback(r) {
			if (r.exc) return;
			frm.reload_doc();
		},
	});
}

// ---------------------------------------------------------------------------
// Financial status helpers
// ---------------------------------------------------------------------------

function _set_financial_indicator(frm) {
	const status = frm.doc.financial_status || "Regular";
	const color  = _FINANCIAL_COLORS[status] || "gray";
	frm.page.set_indicator(__(status), color);
}

function _load_financial_summary(frm) {
	frappe.call({
		method: "escola.escola.doctype.billing_cycle.penalty.get_student_financial_summary",
		args:   { student_name: frm.doc.name },
		callback(r) {
			if (r.exc || !r.message) return;
			const d = r.message;

			if (d.alert_level === 0) {
				frm.dashboard.set_headline("");
				return;
			}

			const color      = _FINANCIAL_COLORS[d.financial_status] || "gray";
			const alert_text = __(_ALERT_MESSAGES[d.alert_level] || "");

			const parts = [
				`<b style="color:var(--${color}-600)">${alert_text}</b>`,
				__("Em dívida: {0}", [format_currency(d.total_outstanding)]),
			];

			if (d.penalty_rate > 0)
				parts.push(__("Multa: {0}% = {1}", [d.penalty_rate, format_currency(d.penalty_amount)]));
			if (d.days_overdue > 0)
				parts.push(__("{0} dias em atraso ({1} período(s))", [d.days_overdue, d.periods]));
			if (d.total_with_penalty > d.total_outstanding)
				parts.push(__("Total com multa: {0}", [format_currency(d.total_with_penalty)]));

			frm.dashboard.set_headline(parts.join(" &nbsp;|&nbsp; "));
		},
	});
}

// ---------------------------------------------------------------------------
// Academic history — inline compact panel
// ---------------------------------------------------------------------------

function _load_academic_history(frm) {
	const fd = frm.fields_dict["student_history_html"];
	if (!fd) return;

	fd.$wrapper.html(
		`<div style="color:var(--text-muted);font-size:12px;padding:4px 0;">${__("A carregar historial...")}</div>`
	);

	frappe.call({
		method: "escola.escola.doctype.student.student.get_student_academic_history",
		args:   { student: frm.doc.name },
		callback(r) {
			frm._academic_history = r.message || [];
			if (r.exc) {
				fd.$wrapper.html(
					`<div style="color:var(--text-muted);font-size:13px;">${__("Não foi possível carregar o historial.")}</div>`
				);
				return;
			}
			fd.$wrapper.html(_render_history_compact(frm._academic_history));
		},
	});
}

function _render_history_compact(data) {
	if (!data || !data.length) {
		return `<div style="color:var(--text-muted);font-size:13px;padding:6px 0;">${__("Sem historial académico registado.")}</div>`;
	}

	const RESULT_COLOR = {
		"Aprovado":  "#16a34a",
		"Reprovado": "#dc2626",
		"Concluído": "#16a34a",
	};

	return data.map(yr => {
		const rc = RESULT_COLOR[yr.final_decision];
		const statusStyle = yr.sga_status === "Activa"
			? "background:#dcfce7;color:#166534;"
			: "background:#f3f4f6;color:#6b7280;";

		const tags = [
			yr.final_decision ? `<span style="color:${rc || "#374151"};font-weight:600;font-size:12px;">${__(yr.final_decision)}</span>` : "",
			yr.overall_average != null ? `<span style="font-size:12px;color:#374151;">${__("Média")}: <b>${yr.overall_average}</b></span>` : "",
			yr.total_absences  != null ? `<span style="font-size:12px;color:#374151;">${__("Faltas")}: <b>${yr.total_absences}</b></span>`  : "",
		].filter(Boolean);

		return `
<div style="display:flex;align-items:center;gap:10px;padding:8px 12px;border:1px solid var(--border-color);border-radius:8px;margin-bottom:6px;background:var(--fg-color);">
  <span style="font-weight:700;font-size:13px;min-width:90px;">${yr.academic_year}</span>
  <span style="font-size:12px;color:var(--text-muted);min-width:70px;">${yr.school_class || "—"}</span>
  <span style="font-size:12px;color:var(--text-muted);min-width:60px;">${yr.class_group || "—"}</span>
  ${yr.sga_status ? `<span style="font-size:11px;font-weight:600;padding:2px 8px;border-radius:12px;${statusStyle}">${__(yr.sga_status)}</span>` : ""}
  <span style="display:flex;gap:10px;flex-wrap:wrap;margin-left:auto;">${tags.join('<span style="color:var(--border-color);">·</span>')}</span>
</div>`;
	}).join("");
}

// ---------------------------------------------------------------------------
// Renewal history panel
// ---------------------------------------------------------------------------

async function _load_renewal_status(frm) {
	const fd = frm.fields_dict["renovation_status_html"];
	if (!fd) return;

	fd.$wrapper.html("");

	const r = await frappe.call({
		method: "escola.escola.doctype.renovacao_de_matricula.renovacao_de_matricula.get_student_renewal_history",
		args:   { student: frm.doc.name, limit: 5 },
	});

	if (r.exc || !r.message) return;

	_inject_student_styles();
	const d = r.message;

	// Keep frm._renewal_status populated for the actions modal
	frm._renewal_status = {
		in_period:    d.in_period,
		period_start: d.period_start,
		period_end:   d.period_end,
		current_year: d.current_year,
		next_year:    d.next_year,
		renewal:      d.current_renewal,
	};

	fd.$wrapper.html(_render_renewal_history(frm, d));

	fd.$wrapper.find("[data-name]").on("click", function () {
		frappe.set_route("Form", "Renovacao De Matricula", $(this).data("name"));
	});
	fd.$wrapper.find("[data-action=new-renewal]").on("click", function () {
		_open_new_renewal(frm, d);
	});
}

function _render_renewal_history(frm, d) {
	const listUrl = `/app/renovacao-de-matricula?student=${encodeURIComponent(frm.doc.name)}`;

	const header = `
	<div class="srn-header">
		<span class="srn-title">${__("Renovações de Matrícula")}</span>
		<a class="srn-all-link" href="${listUrl}" target="_blank">↗ ${__("Ver todas")}</a>
	</div>`;

	// Pending action row — only when window is open, not yet renewed, and student can still renew
	let pendingRow = "";
	if (d.in_period && !d.current_renewal && frm.doc.current_status !== "Concluiu") {
		const end_fmt = frappe.datetime.str_to_user(d.period_end);
		pendingRow = `
		<div class="srn-pending">
			<span>⚠</span>
			<span>${__("Período aberto até {0} — matrícula por renovar", [end_fmt])}</span>
			<button class="srn-pending-btn" data-action="new-renewal">${__("Renovar Agora")}</button>
		</div>`;
	}

	if (!d.renewals || !d.renewals.length) {
		return header + pendingRow + `<div class="srn-empty">${__("Sem renovações registadas.")}</div>`;
	}

	const rows = d.renewals.map(ren => {
		const date_fmt  = frappe.datetime.str_to_user(ren.renewal_date);
		const confirmed = ren.docstatus === 1;
		const badge     = confirmed
			? `<span class="srn-badge confirmed">${__("Confirmada")}</span>`
			: `<span class="srn-badge draft">${__("Rascunho")}</span>`;

		return `
		<div class="srn-row">
			<div class="srn-row-top">
				<span class="srn-years">${frappe.utils.escape_html(ren.academic_year)} → ${frappe.utils.escape_html(ren.target_academic_year)}</span>
				<button class="srn-ver" data-name="${frappe.utils.escape_html(ren.name)}">${__("Ver →")}</button>
			</div>
			<div class="srn-row-bottom">
				<span class="srn-date">${date_fmt}</span>
				${badge}
			</div>
		</div>`;
	}).join("");

	return header + pendingRow + rows;
}

function _open_new_renewal(frm, renewal_data) {
	frappe.new_doc("Renovacao De Matricula", {
		student:              frm.doc.name,
		academic_year:        renewal_data.current_year,
		target_academic_year: renewal_data.next_year || "",
	});
}

// ---------------------------------------------------------------------------
// Invoices modal
// ---------------------------------------------------------------------------

async function _show_invoices_modal(frm) {
	_inject_student_styles();

	const d = new frappe.ui.Dialog({
		title: `🧾 ${__("Facturas")} · ${frm.doc.full_name}`,
		size:  "extra-large",
	});
	d.$body.css("padding", "0");
	d.$body.html(`<div style="padding:24px;color:#9ca3af;font-size:13px;">${__("A carregar facturas…")}</div>`);
	d.set_secondary_action_label(__("Fechar"));
	d.set_secondary_action(() => d.hide());
	d.$wrapper.find(".btn-modal-primary").hide();
	d.show();

	const r = await frappe.call({
		method: "escola.escola.doctype.student.student.get_student_invoices",
		args:   { student: frm.doc.name },
	});

	if (r.exc || !r.message) {
		d.$body.html(`<div class="sinv-empty">${__("Não foi possível carregar as facturas.")}</div>`);
		return;
	}

	const { invoices, summary } = r.message;
	d.$body.html(_render_invoices(invoices, summary, frm.doc.name));
}

const _INV_STATUS = {
	"Paga":      { bg: "#dcfce7", fg: "#166534" },
	"Emitida":   { bg: "#dbeafe", fg: "#1e40af" },
	"Em Atraso": { bg: "#fee2e2", fg: "#991b1b" },
	"Rascunho":  { bg: "#f3f4f6", fg: "#6b7280" },
};

function _render_invoices(invoices, summary, student_name) {
	const fmt = v => format_currency(v);

	// Summary cards
	const summaryHtml = `
<div class="sinv-summary">
  <div class="sinv-card" style="background:#eff6ff;color:#1e40af;">
    <div class="sinv-card-label">${__("Total Facturado")}</div>
    <div class="sinv-card-val">${fmt(summary.total_invoiced)}</div>
    <div style="font-size:11px;margin-top:4px;opacity:.7;">${summary.count} ${__("factura(s)")}</div>
  </div>
  <div class="sinv-card" style="background:#f0fdf4;color:#166534;">
    <div class="sinv-card-label">${__("Total Pago")}</div>
    <div class="sinv-card-val">${fmt(summary.total_paid)}</div>
  </div>
  <div class="sinv-card" style="background:${summary.total_outstanding > 0 ? "#fef2f2" : "#f8fafc"};color:${summary.total_outstanding > 0 ? "#991b1b" : "#374151"};">
    <div class="sinv-card-label">${__("Em Aberto")}</div>
    <div class="sinv-card-val">${fmt(summary.total_outstanding)}</div>
  </div>
</div>`;

	if (!invoices.length) {
		return `<div style="padding:24px;">${summaryHtml}<div class="sinv-empty">${__("Nenhuma factura encontrada.")}</div></div>`;
	}

	const rows = invoices.map(inv => {
		const st = _INV_STATUS[inv.status] || { bg: "#f3f4f6", fg: "#6b7280" };
		const outstanding_html = inv.outstanding > 0
			? `<span style="color:#dc2626;font-weight:600;">${fmt(inv.outstanding)}</span>`
			: `<span style="color:#9ca3af;">—</span>`;
		return `<tr>
			<td>
				<a class="sinv-link" href="/app/sales-invoice/${encodeURIComponent(inv.name)}" target="_blank">${frappe.utils.escape_html(inv.name)}</a>
			</td>
			<td>${inv.mes_referencia !== "—" ? `<span style="font-weight:500;">${frappe.utils.escape_html(inv.mes_referencia)}</span>` : "<span style='color:#9ca3af;'>—</span>"}</td>
			<td style="color:#374151;">${inv.posting_date}</td>
			<td style="color:${inv.status === 'Em Atraso' ? '#dc2626' : '#374151'};">${inv.due_date}</td>
			<td class="num">${fmt(inv.grand_total)}</td>
			<td class="num">${fmt(inv.paid)}</td>
			<td class="num">${outstanding_html}</td>
			<td><span class="sinv-badge" style="background:${st.bg};color:${st.fg};">${__(inv.status)}</span></td>
		</tr>`;
	}).join("");

	const listUrl = `/app/sales-invoice?escola_student=${encodeURIComponent(student_name)}`;

	return `
<div style="padding:24px;">
  ${summaryHtml}
  <div style="overflow-x:auto;border:1px solid #e2e8f0;border-radius:10px;">
    <table class="sinv-table">
      <thead>
        <tr>
          <th>${__("Factura")}</th>
          <th>${__("Mês")}</th>
          <th>${__("Emissão")}</th>
          <th>${__("Vencimento")}</th>
          <th class="num">${__("Total")}</th>
          <th class="num">${__("Pago")}</th>
          <th class="num">${__("Em Aberto")}</th>
          <th>${__("Estado")}</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  </div>
  <div class="sinv-footer">
    <a href="${listUrl}" target="_blank">↗ ${__("Abrir lista completa")}</a>
  </div>
</div>`;
}

// ---------------------------------------------------------------------------
// Services modal (Mensalidade Extra do Aluno)
// ---------------------------------------------------------------------------

async function _show_services_modal(frm) {
	_inject_student_styles();

	const d = new frappe.ui.Dialog({
		title: `🔧 ${__("Serviços Extras")} · ${frm.doc.full_name}`,
		size: "large",
	});
	d.$body.css("padding", "0");
	d.$body.html(`<div style="padding:24px;color:#9ca3af;font-size:13px;">${__("A carregar serviços…")}</div>`);
	d.set_secondary_action_label(__("Fechar"));
	d.set_secondary_action(() => d.hide());
	d.$wrapper.find(".btn-modal-primary").hide();
	d.show();

	const r = await frappe.call({
		method: "escola.escola.doctype.mensalidade_extra_do_aluno.mensalidade_extra_do_aluno.get_active_services_for_student",
		args: { student: frm.doc.name },
	});

	const services = r.message || [];
	const fmt = v => format_currency(v);

	if (!services.length) {
		const mea = await frappe.db.get_value("Mensalidade Extra do Aluno", { student: frm.doc.name }, "name").catch(() => null);
		const linkHtml = mea && mea.message
			? `<br><a style="color:#2563eb;font-size:12px;" href="/app/mensalidade-extra-do-aluno/${encodeURIComponent(mea.message.name)}">${__("Abrir registo →")}</a>`
			: `<br><a style="color:#2563eb;font-size:12px;" href="/app/mensalidade-extra-do-aluno/new-mensalidade-extra-do-aluno">${__("Criar registo →")}</a>`;
		d.$body.html(`<div style="padding:40px;text-align:center;color:#9ca3af;font-size:14px;">${__("Sem serviços extras activos.")}${linkHtml}</div>`);
		return;
	}

	const total = services.reduce((s, r) => s + r.current_amount, 0);
	const mea_name = services[0] && await frappe.db.get_value("Mensalidade Extra do Aluno", { student: frm.doc.name }, "name");

	const fmtDate = d => d ? frappe.datetime.str_to_user(d) : null;

	const rows = services.map(s => {
		const start = fmtDate(s.start_date) || "—";
		const end   = s.end_date
			? `<span style="color:#991b1b;">${fmtDate(s.end_date)}</span>`
			: `<span style="background:#d1fae5;color:#065f46;font-size:10px;font-weight:700;padding:2px 7px;border-radius:10px;">Em curso</span>`;
		return `
		<tr style="border-bottom:1px solid #f1f5f9;">
			<td style="padding:10px 14px;font-size:13px;font-weight:500;color:#1e293b;">${frappe.utils.escape_html(s.service_name)}</td>
			<td style="padding:10px 14px;font-size:12px;color:#475569;text-align:center;">${start}</td>
			<td style="padding:10px 14px;font-size:12px;text-align:center;">${end}</td>
			<td style="padding:10px 14px;font-size:13px;text-align:right;font-variant-numeric:tabular-nums;">${fmt(s.current_amount)}</td>
		</tr>`;
	}).join("");

	const docUrl = mea_name && mea_name.message
		? `/app/mensalidade-extra-do-aluno/${encodeURIComponent(mea_name.message.name)}`
		: null;

	d.$body.html(`
	<div style="padding:24px;">
		<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;">
			<div style="font-size:13px;color:#64748b;">${__("Serviços activos neste momento")}</div>
			<div style="font-size:18px;font-weight:800;color:#0f766e;">${fmt(total)} <span style="font-size:12px;font-weight:500;color:#94a3b8;">/ mês</span></div>
		</div>
		<div style="border:1px solid #e2e8f0;border-radius:10px;overflow:hidden;">
			<table style="width:100%;border-collapse:collapse;">
				<thead>
					<tr style="background:#f0fdfa;">
						<th style="padding:8px 14px;text-align:left;font-size:11px;font-weight:700;color:#0f766e;text-transform:uppercase;letter-spacing:.05em;">${__("Serviço")}</th>
						<th style="padding:8px 14px;text-align:center;font-size:11px;font-weight:700;color:#0f766e;text-transform:uppercase;letter-spacing:.05em;">${__("Início")}</th>
						<th style="padding:8px 14px;text-align:center;font-size:11px;font-weight:700;color:#0f766e;text-transform:uppercase;letter-spacing:.05em;">${__("Fim")}</th>
						<th style="padding:8px 14px;text-align:right;font-size:11px;font-weight:700;color:#0f766e;text-transform:uppercase;letter-spacing:.05em;">${__("Valor/Mês")}</th>
					</tr>
				</thead>
				<tbody style="font-size:13px;">${rows}</tbody>
			</table>
		</div>
		${docUrl ? `<div style="margin-top:12px;text-align:right;"><a href="${docUrl}" target="_blank" style="font-size:12px;color:#6366f1;text-decoration:none;">↗ ${__("Gerir serviços")}</a></div>` : ""}
	</div>`);
}

// ---------------------------------------------------------------------------
// Forecast modal
// ---------------------------------------------------------------------------

const _FORECAST_STATUS = {
	"Previsto":  { bg: "#f1f5f9", fg: "#475569", dot: "#94a3b8" },
	"Rascunho":  { bg: "#f3f4f6", fg: "#6b7280", dot: "#9ca3af" },
	"Facturado": { bg: "#fef3c7", fg: "#92400e", dot: "#f59e0b" },
	"Pago":      { bg: "#d1fae5", fg: "#065f46", dot: "#10b981" },
};

async function _show_forecast_modal(frm) {
	_inject_student_styles();

	const d = new frappe.ui.Dialog({
		title: `📅 ${__("Previsão Financeira")} · ${frm.doc.full_name}`,
		size:  "extra-large",
	});
	d.$body.css("padding", "0");
	d.$body.html(`<div style="padding:24px;color:#9ca3af;font-size:13px;">${__("A carregar previsão…")}</div>`);
	d.set_secondary_action_label(__("Fechar"));
	d.set_secondary_action(() => d.hide());
	d.$wrapper.find(".btn-modal-primary").hide();
	d.show();

	const r = await frappe.call({
		method: "escola.escola.billing_forecast.get_student_forecast",
		args:   { student_name: frm.doc.name },
	});

	if (r.exc || !r.message) {
		d.$body.html(`<div style="padding:24px;color:#ef4444;font-size:13px;">${__("Não foi possível carregar a previsão.")}</div>`);
		return;
	}

	const fc = r.message;
	d.$body.html(_render_forecast(fc));
}

function _render_forecast(fc) {
	const fmt = v => format_currency(v);
	const s   = fc.summary || {};

	if (fc.is_bolsista) {
		return `<div style="padding:40px;text-align:center;color:#9ca3af;font-size:14px;">
			${__("Aluno Bolsista — isento de facturação.")}
		</div>`;
	}

	if (!fc.periods || !fc.periods.length) {
		return `<div style="padding:40px;text-align:center;color:#9ca3af;font-size:14px;">
			${__("Nenhum período de facturação encontrado para o ano lectivo actual.")}
		</div>`;
	}

	const summaryHtml = `
<div class="sfrc-summary">
  <div class="sfrc-stat" style="background:#eff6ff;color:#1e40af;">
    <div class="sfrc-stat-label">${__("Total Previsto")}</div>
    <div class="sfrc-stat-val">${fmt(s.total_expected)}</div>
    <div style="font-size:11px;margin-top:4px;opacity:.7;">${fc.academic_year || ""}</div>
  </div>
  <div class="sfrc-stat" style="background:#f0fdf4;color:#166534;">
    <div class="sfrc-stat-label">${__("Pago")}</div>
    <div class="sfrc-stat-val">${fmt(s.total_paid)}</div>
    <div style="font-size:11px;margin-top:4px;opacity:.7;">${s.count_pago || 0} ${__("per.")}</div>
  </div>
  <div class="sfrc-stat" style="background:${(s.total_outstanding || 0) > 0 ? "#fef2f2" : "#f8fafc"};color:${(s.total_outstanding || 0) > 0 ? "#991b1b" : "#374151"};">
    <div class="sfrc-stat-label">${__("Em Dívida")}</div>
    <div class="sfrc-stat-val">${fmt(s.total_outstanding)}</div>
    <div style="font-size:11px;margin-top:4px;opacity:.7;">${s.count_facturado || 0} ${__("per.")}</div>
  </div>
  <div class="sfrc-stat" style="background:#f8fafc;color:#64748b;">
    <div class="sfrc-stat-label">${__("A Emitir")}</div>
    <div class="sfrc-stat-val">${fmt(s.total_previsto)}</div>
    <div style="font-size:11px;margin-top:4px;opacity:.7;">${s.count_previsto || 0} ${__("per.")}</div>
  </div>
</div>`;

	const today = frappe.datetime.get_today();
	const rows  = fc.periods.map(p => {
		const st = _FORECAST_STATUS[p.status] || _FORECAST_STATUS["Previsto"];
		const isPastDue = p.due_date < today && p.status === "Facturado";
		const rowBg     = isPastDue ? "background:#fff5f5;" : "";
		const invLink   = p.invoice_name
			? p.is_advance
				? `<a class="sinv-link" href="/app/adiantamento-de-pagamento/${encodeURIComponent(p.adiantamento || p.invoice_name)}" target="_blank" title="${__('Adiantamento de Pagamento')}">${__("Adiantamento")}</a>`
				: `<a class="sinv-link" href="/app/sales-invoice/${encodeURIComponent(p.invoice_name)}" target="_blank">${frappe.utils.escape_html(p.invoice_name)}</a>`
			: "<span style='color:#cbd5e1;'>—</span>";
		const amtDisplay = p.status === "Pago"
			? `<span style="color:#059669;font-weight:600;">${fmt(p.amount)}</span>`
			: p.status === "Facturado"
				? `<span style="color:#92400e;font-weight:600;">${fmt(p.outstanding)}</span>`
				: `<span style="color:#64748b;">${fmt(p.amount)}</span>`;
		return `<tr style="${rowBg}">
			<td style="font-weight:600;">${frappe.utils.escape_html(p.period_label)}</td>
			<td style="color:#64748b;">${frappe.utils.escape_html(p.billing_mode)}</td>
			<td style="color:${isPastDue ? "#dc2626" : "#374151"};">${p.due_date}</td>
			<td class="num">${amtDisplay}</td>
			<td>
				<span class="sfrc-badge" style="background:${st.bg};color:${st.fg};">
					<span class="sfrc-dot" style="background:${st.dot};"></span>
					${__(p.status)}
				</span>
			</td>
			<td>${invLink}</td>
		</tr>`;
	}).join("");

	return `
<div style="padding:24px;">
  ${summaryHtml}
  <div style="overflow-x:auto;border:1px solid #e2e8f0;border-radius:10px;">
    <table class="sinv-table">
      <thead>
        <tr>
          <th>${__("Período")}</th>
          <th>${__("Modo")}</th>
          <th>${__("Vencimento")}</th>
          <th class="num">${__("Valor")}</th>
          <th>${__("Estado")}</th>
          <th>${__("Factura")}</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  </div>
</div>`;
}

// ---------------------------------------------------------------------------
// Timeline modal
// ---------------------------------------------------------------------------

async function _show_timeline_modal(frm) {
	// Use cached data if already loaded, otherwise fetch
	if (!frm._academic_history) {
		const r = await frappe.call({
			method: "escola.escola.doctype.student.student.get_student_academic_history",
			args:   { student: frm.doc.name },
			freeze: false,
		});
		frm._academic_history = r.message || [];
	}

	const d = new frappe.ui.Dialog({
		title: `🕐 ${__("Historial Académico")} · ${frm.doc.full_name}`,
		size:  "large",
	});

	d.$body.css("padding", "0");
	d.$body.html(_render_timeline(frm._academic_history));
	d.set_secondary_action_label(__("Fechar"));
	d.set_secondary_action(() => d.hide());
	d.$wrapper.find(".btn-modal-primary").hide();
	d.show();
}

function _render_timeline(data) {
	if (!data || !data.length) {
		return `<div class="stl-empty">${__("Sem historial académico registado.")}</div>`;
	}

	const RESULT = {
		"Aprovado":  { dot: "#16a34a", text: "#15803d", bg: "#f0fdf4" },
		"Reprovado": { dot: "#dc2626", text: "#dc2626", bg: "#fef2f2" },
		"Concluído": { dot: "#16a34a", text: "#15803d", bg: "#f0fdf4" },
	};
	const SGA_STATUS = {
		"Activa":      { bg: "#dcfce7", fg: "#166534" },
		"Encerrada":   { bg: "#f3f4f6", fg: "#6b7280" },
		"Transferida": { bg: "#fef3c7", fg: "#92400e" },
	};

	const items = data.map((yr, i) => {
		const rc = RESULT[yr.final_decision] || { dot: "#9ca3af", text: "#374151", bg: "var(--fg-color)" };
		const sc = SGA_STATUS[yr.sga_status]  || SGA_STATUS["Encerrada"];
		const isLast = i === data.length - 1;

		const stats = [
			{ label: __("Classe"), val: yr.school_class || "—" },
			{ label: __("Turma"),  val: yr.class_group  || "—" },
			yr.overall_average != null ? { label: __("Média"),  val: yr.overall_average, color: rc.text, bold: true } : null,
			yr.total_absences  != null ? { label: __("Faltas"), val: yr.total_absences } : null,
		].filter(Boolean);

		const statsHtml = stats.map(st => `
			<div class="stl-stat">
				<div class="stl-stat-label">${st.label}</div>
				<div class="stl-stat-val" style="${st.color ? `color:${st.color};` : ""}${st.bold ? "font-weight:700;" : ""}">${st.val}</div>
			</div>
		`).join("");

		const footLinks = [
			yr.report_card ? `<a href="/app/report-card/${encodeURIComponent(yr.report_card)}" target="_blank">📋 ${__("Ver Boletim")} →</a>` : "",
			yr.class_group  ? `<a href="/app/class-group/${encodeURIComponent(yr.class_group)}"  target="_blank">👥 ${__("Ver Turma")}  →</a>` : "",
		].filter(Boolean).join("");

		return `
<div class="stl-item">
  <div class="stl-spine">
    <div class="stl-dot" style="background:${rc.dot};box-shadow:0 0 0 3px ${rc.dot}28;"></div>
    ${!isLast ? '<div class="stl-line"></div>' : ""}
  </div>
  <div class="stl-card">
    <div class="stl-head" style="background:${rc.bg};">
      <div style="display:flex;align-items:center;">
        <span class="stl-year">${yr.academic_year}</span>
        ${yr.sga_status ? `<span class="stl-status-badge" style="background:${sc.bg};color:${sc.fg};">${__(yr.sga_status)}</span>` : ""}
      </div>
      ${yr.final_decision ? `<span class="stl-result" style="color:${rc.text};">${__(yr.final_decision)}</span>` : ""}
    </div>
    <div class="stl-body">${statsHtml}</div>
    ${footLinks ? `<div class="stl-foot">${footLinks}</div>` : ""}
  </div>
</div>`;
	});

	return `<div class="stl-wrap" style="padding:16px 20px;">${items.join("")}</div>`;
}

// ---------------------------------------------------------------------------
// Full name / age sync
// ---------------------------------------------------------------------------

function update_age(frm) {
	if (!frm.doc.date_of_birth) return;
	const dob   = frappe.datetime.str_to_obj(frm.doc.date_of_birth);
	const today = new Date();
	let age = today.getFullYear() - dob.getFullYear();
	if (
		today.getMonth() < dob.getMonth() ||
		(today.getMonth() === dob.getMonth() && today.getDate() < dob.getDate())
	) age--;
	frm.set_value("idade", age >= 0 ? age : null);
}

function update_full_name(frm) {
	const parts = [frm.doc.first_name, frm.doc.last_name].filter(Boolean);
	frm.set_value("full_name", parts.join(" "));
}

// ---------------------------------------------------------------------------
// Student results modal — inline grade card
// ---------------------------------------------------------------------------

async function _show_student_results_modal(frm) {
	const d = new frappe.ui.Dialog({
		title: `📊 ${__("Resultados")} · ${frm.doc.full_name}`,
		size:  "extra-large",
	});
	d.$body.css("padding", "16px 20px");
	d.$body.html(`<div style="text-align:center;padding:40px;color:var(--text-muted);">
		<i class="fa fa-spinner fa-spin fa-2x"></i>
		<div style="margin-top:10px;">${__("A carregar resultados…")}</div>
	</div>`);
	d.$wrapper.find(".btn-modal-primary").hide();
	d.set_secondary_action_label(__("Fechar"));
	d.set_secondary_action(() => d.hide());
	d.show();

	const r = await frappe.call({
		method: "escola.escola.page.boletim_aluno.boletim_aluno.get_student_report",
		args:   { student: frm.doc.name },
	});

	if (r.exc || !r.message) {
		d.$body.html(`<div style="text-align:center;padding:40px;color:var(--text-muted);">${__("Não foi possível carregar os resultados.")}</div>`);
		return;
	}

	const data = r.message;
	d.$body.html(_render_results_card(frm, data));

	d.$body.find(".sr-goto-boletim").on("click", () => {
		d.hide();
		frappe.route_options = { student: frm.doc.name };
		frappe.set_route("boletim-aluno");
	});
}

function _render_results_card(frm, data) {
	const esc   = (v) => frappe.utils.escape_html(v || "");
	const fmt   = (v) => (v !== null && v !== undefined) ? String(Math.round(parseFloat(v))) : "—";
	const initials = (frm.doc.first_name || "?")[0].toUpperCase();

	const STATUS_COLOR = {
		"Activo":              { bg: "#dcfce7", fg: "#166534" },
		"Pendente de Turma":   { bg: "#fef9c3", fg: "#854d0e" },
		"Pendente de Renovação": { bg: "#fef3c7", fg: "#92400e" },
		"Transferido":         { bg: "#dbeafe", fg: "#1d4ed8" },
		"Desistente":          { bg: "#fee2e2", fg: "#dc2626" },
		"Concluiu":            { bg: "#f3f4f6", fg: "#374151" },
	};
	const sc = STATUS_COLOR[data.current_status] || STATUS_COLOR["Activo"];
	const statusBadge = `<span style="font-size:11px;font-weight:600;padding:2px 10px;border-radius:12px;background:${sc.bg};color:${sc.fg};">${esc(__(data.current_status))}</span>`;

	const turmaLine = frm.doc.current_class_group
		? `<a href="/app/class-group/${encodeURIComponent(frm.doc.current_class_group)}" target="_blank"
		      style="font-size:12px;color:var(--primary);">${esc(frm.doc.current_class_group)}</a>`
		: `<span style="font-size:12px;color:var(--text-muted);">${__("Sem turma")}</span>`;

	// Header
	let html = `
		<div style="display:flex;align-items:center;gap:14px;margin-bottom:18px;padding-bottom:14px;border-bottom:1px solid var(--border-color);">
			<div style="width:46px;height:46px;border-radius:50%;background:var(--primary-light);display:flex;align-items:center;justify-content:center;font-size:20px;font-weight:800;color:var(--primary);flex-shrink:0;">
				${esc(initials)}
			</div>
			<div style="flex:1;min-width:0;">
				<div style="font-weight:700;font-size:16px;color:var(--heading-color);">${esc(data.full_name)}</div>
				<div style="display:flex;align-items:center;gap:8px;margin-top:3px;flex-wrap:wrap;">
					${data.student_code ? `<span style="font-size:12px;color:var(--text-muted);font-family:monospace;">${esc(data.student_code)}</span>` : ""}
					${turmaLine}
					${statusBadge}
				</div>
			</div>
		</div>
	`;

	if (!data.years || !data.years.length) {
		html += `<div style="text-align:center;padding:32px;color:var(--text-muted);">${__("Sem resultados académicos registados.")}</div>`;
	} else {
		const RESULT_STYLE = {
			"Promovido":  { bg: "#dcfce7", fg: "#166534", ico: "✓" },
			"Aprovado":   { bg: "#dcfce7", fg: "#166534", ico: "✓" },
			"Retido":     { bg: "#fee2e2", fg: "#dc2626", ico: "✕" },
			"Reprovado":  { bg: "#fee2e2", fg: "#dc2626", ico: "✕" },
			"Concluído":  { bg: "#dbeafe", fg: "#1d4ed8", ico: "★" },
		};

		data.years.forEach(yr => {
			const rs = RESULT_STYLE[yr.final_decision] || null;
			const resultBadge = rs
				? `<span style="font-size:11px;font-weight:700;padding:2px 10px;border-radius:12px;background:${rs.bg};color:${rs.fg};">${rs.ico} ${esc(__(yr.final_decision))}</span>`
				: "";
			const overallBadge = yr.overall_average != null
				? `<span style="font-size:12px;font-weight:700;color:var(--primary);">${__("Média")}: ${fmt(yr.overall_average)}</span>`
				: "";
			const absencesBadge = yr.total_absences != null
				? `<span style="font-size:12px;color:var(--text-muted);">${__("Faltas")}: ${yr.total_absences}</span>`
				: "";

			// Term header cells
			const termHeaders = (yr.term_labels || []).map((tl, i) =>
				`<th style="background:#1E293B;color:white;padding:6px 8px;font-size:11px;text-align:center;white-space:nowrap;">
					${esc(tl)}
				</th>`
			).join("");

			// Subject rows
			const subjectRows = (yr.subjects || []).map(s => {
				const termCells = (s.term_grades || []).map(g =>
					`<td style="text-align:center;font-size:12px;padding:4px 6px;">${g !== null && g !== undefined ? Math.round(g) : "—"}</td>`
				).join("");
				const mf = s.annual_average;
				const mfColor = mf !== null ? (mf >= 10 ? "#065F46" : "#991B1B") : "inherit";
				return `
					<tr style="border-bottom:1px solid var(--border-color);">
						<td style="padding:5px 8px;font-size:12px;font-weight:500;">${esc(s.subject)}</td>
						${termCells}
						<td style="text-align:center;font-size:12px;font-weight:700;padding:4px 8px;color:${mfColor};">${fmt(mf)}</td>
					</tr>`;
			}).join("");

			// Averages footer row
			const avgCells = (yr.term_averages || []).map(a =>
				`<td style="text-align:center;font-size:12px;font-weight:700;padding:5px 6px;">${a !== null && a !== undefined ? Math.round(a) : "—"}</td>`
			).join("");

			// Comportamento abbreviation helper
			const abbr = (v) => {
				if (!v) return "—";
				const m = { "Muito Bom":"MB","Bom":"B","Satisfatório":"S","Suficiente":"SF","Insatisfatório":"I","Mau":"M","Muito Mau":"MM" };
				return m[v] || v.substring(0, 2).toUpperCase();
			};

			// Per-term faltas and comportamento rows
			const attendance = yr.term_attendance || [];
			const faltasCells = attendance.map(a =>
				`<td style="text-align:center;font-size:12px;padding:4px 6px;">${a.total !== null && a.total !== undefined ? a.total : "—"}</td>`
			).join("");
			const totalFaltas = yr.total_absences !== null && yr.total_absences !== undefined
				? yr.total_absences : "—";

			const compCells = attendance.map(a => {
				const short = abbr(a.comportamento);
				const color = !a.comportamento ? "var(--text-muted)"
					: (a.comportamento === "Muito Bom" || a.comportamento === "Bom") ? "#065F46"
					: (a.comportamento === "Insatisfatório" || a.comportamento === "Mau" || a.comportamento === "Muito Mau") ? "#991B1B"
					: "#374151";
				return `<td style="text-align:center;font-size:12px;padding:4px 6px;color:${color};font-weight:600;" title="${esc(a.comportamento || "")}">${short}</td>`;
			}).join("");
			const annualComp = yr.comportamento_anual ? abbr(yr.comportamento_anual) : "—";
			const annualCompColor = !yr.comportamento_anual ? "var(--text-muted)"
				: (yr.comportamento_anual === "Muito Bom" || yr.comportamento_anual === "Bom") ? "#065F46"
				: (yr.comportamento_anual === "Insatisfatório" || yr.comportamento_anual === "Mau" || yr.comportamento_anual === "Muito Mau") ? "#991B1B"
				: "#374151";

			html += `
				<div style="margin-bottom:22px;">
					<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;flex-wrap:wrap;">
						<span style="font-weight:700;font-size:14px;">${esc(yr.academic_year)}</span>
						<span style="font-size:12px;color:var(--text-muted);">${esc(yr.school_class || "")}${yr.class_group ? " · " + esc(yr.class_group) : ""}</span>
						${resultBadge}
						${overallBadge}
					</div>
					<div style="overflow-x:auto;">
					<table style="width:100%;border-collapse:collapse;">
						<thead>
							<tr>
								<th style="background:#1E293B;color:white;padding:6px 8px;font-size:11px;text-align:left;min-width:140px;">${__("Disciplina")}</th>
								${termHeaders}
								<th style="background:#374151;color:white;padding:6px 8px;font-size:11px;text-align:center;">${__("MF")}</th>
							</tr>
						</thead>
						<tbody>
							${subjectRows}
							<tr style="background:#F0F4FF;">
								<td style="padding:5px 8px;font-size:11px;font-weight:700;color:#374151;">${__("Média da Turma")}</td>
								${avgCells}
								<td style="text-align:center;font-size:12px;font-weight:700;padding:5px 8px;color:#6366F1;">${fmt(yr.overall_average)}</td>
							</tr>
							<tr style="background:#FFF7ED;border-top:2px solid #E5E7EB;">
								<td style="padding:4px 8px;font-size:11px;font-weight:700;color:#92400E;">${__("Faltas")}</td>
								${faltasCells}
								<td style="text-align:center;font-size:12px;font-weight:700;padding:4px 8px;color:#92400E;">${totalFaltas}</td>
							</tr>
							<tr style="background:#F0FDF4;">
								<td style="padding:4px 8px;font-size:11px;font-weight:700;color:#166534;">${__("Comportamento")}</td>
								${compCells}
								<td style="text-align:center;font-size:12px;font-weight:700;padding:4px 8px;color:${annualCompColor};"
								    title="${esc(yr.comportamento_anual || "")}">${annualComp}</td>
							</tr>
						</tbody>
					</table>
					</div>
				</div>
			`;
		});
	}

	html += `
		<div style="text-align:right;padding-top:8px;border-top:1px solid var(--border-color);margin-top:4px;">
			<button class="btn btn-default btn-sm sr-goto-boletim">
				${__("Ver Boletim Completo")} →
			</button>
		</div>
	`;

	return html;
}

// ---------------------------------------------------------------------------
// Reactivation dialog (existing, unchanged)
// ---------------------------------------------------------------------------

function _register_withdrawal_dialog(frm) {
	const d = new frappe.ui.Dialog({
		title: __("Registar Desistência — {0}", [frm.doc.full_name]),
		fields: [
			{
				fieldname:  "withdrawal_date",
				fieldtype:  "Date",
				label:      __("Data de Desistência"),
				reqd:       1,
				default:    frappe.datetime.get_today(),
			},
			{
				fieldname:  "withdrawal_reason",
				fieldtype:  "Small Text",
				label:      __("Motivo"),
				reqd:       1,
				description: __("Descreva o motivo da desistência (será guardado no registo do aluno)."),
			},
		],
		primary_action_label: __("Confirmar Desistência"),
		async primary_action(values) {
			if (!values.withdrawal_date || !(values.withdrawal_reason || "").trim()) return;
			d.hide();

			const r = await frappe.call({
				method:  "escola.escola.doctype.student.student.register_withdrawal",
				args: {
					student:           frm.doc.name,
					withdrawal_date:   values.withdrawal_date,
					withdrawal_reason: values.withdrawal_reason,
				},
				freeze:         true,
				freeze_message: __("A registar desistência…"),
			});

			if (r.exc) return;
			frappe.show_alert({
				message:   __("Desistência registada. O aluno foi removido da turma."),
				indicator: "orange",
			}, 5);
			frm.reload_doc();
		},
	});
	d.show();
}

function reactivate_dialog(frm) {
	const d = new frappe.ui.Dialog({
		title: __("Reactivar {0}", [frm.doc.full_name]),
		fields: [
			{
				fieldname: "academic_year",
				fieldtype: "Link",
				options:   "Academic Year",
				label:     __("Ano Lectivo"),
				reqd:      1,
				onchange() {
					d.set_value("class_group", null);
					d.fields_dict.class_group.get_query = () => ({ filters: build_filters(d) });
				},
			},
			{
				fieldname: "school_class",
				fieldtype: "Link",
				options:   "School Class",
				label:     __("Classe"),
				get_query: () => ({ filters: { is_active: 1 } }),
				onchange() {
					d.set_value("class_group", null);
					d.fields_dict.class_group.get_query = () => ({ filters: build_filters(d) });
				},
			},
			{
				fieldname:   "class_group",
				fieldtype:   "Link",
				options:     "Class Group",
				label:       __("Turma"),
				reqd:        1,
				get_query:   () => ({ filters: build_filters(d) }),
				description: __("Seleccione a turma para o ano lectivo em curso."),
			},
		],
		primary_action_label: __("Reactivar"),
		primary_action(values) {
			frappe.call({
				method: "escola.escola.doctype.inscricao.inscricao.reactivate_student",
				args: {
					student_name:     frm.doc.name,
					class_group_name: values.class_group,
				},
				callback(r) {
					if (r.exc) return;
					d.hide();
					frappe.show_alert({ message: __("Aluno reactivado e atribuído à turma."), indicator: "green" });
					frm.reload_doc();
				},
			});
		},
	});
	d.show();
}

function build_filters(d) {
	const f  = { is_active: 1 };
	const ay = d.get_value("academic_year");
	const sc = d.get_value("school_class");
	if (ay) f.academic_year = ay;
	if (sc) f.school_class  = sc;
	return f;
}

// ---------------------------------------------------------------------------
// Document panel
// ---------------------------------------------------------------------------

async function _load_documents(frm) {
	const fd = frm.fields_dict["docs_panel_html"];
	if (!fd) return;
	fd.$wrapper.html(
		`<div style="color:var(--text-muted);font-size:13px;padding:6px 0;">${__("A carregar documentos…")}</div>`
	);
	const r = await frappe.call({
		method: "escola.escola.doctype.student.student.get_student_documents",
		args: { student: frm.doc.name },
	});
	_render_docs_panel(frm, r.message || []);
}

function _render_docs_panel(frm, docs) {
	const fd = frm.fields_dict["docs_panel_html"];
	if (!fd) return;

	if (!docs.length) {
		fd.$wrapper.html(
			`<div style="color:var(--text-muted);font-size:13px;padding:6px 0;">${__("Nenhum documento registado para este aluno.")}</div>`
		);
		return;
	}

	const pendingReq = docs.filter(d => d.status === "Pendente" && d.is_required).length;
	const pendingOpt = docs.filter(d => d.status === "Pendente" && !d.is_required).length;

	let badge = "";
	if (pendingReq) {
		badge = `<span style="background:#fef3c7;color:#92400e;font-size:11px;font-weight:600;padding:2px 9px;border-radius:10px;margin-left:8px;">${pendingReq} obrigatório(s) pendente(s)</span>`;
	} else if (pendingOpt) {
		badge = `<span style="background:#f3f4f6;color:#6b7280;font-size:11px;font-weight:600;padding:2px 9px;border-radius:10px;margin-left:8px;">${pendingOpt} opcional(is) pendente(s)</span>`;
	}

	const rows = docs.map(doc => {
		const isPending = doc.status === "Pendente";
		const statusHtml = isPending
			? `<span style="background:#fef3c7;color:#92400e;font-size:11px;font-weight:600;padding:2px 8px;border-radius:10px;">${__("Pendente")}</span>`
			: `<span style="background:#d1fae5;color:#065f46;font-size:11px;font-weight:600;padding:2px 8px;border-radius:10px;">${__("Entregue")}</span>`;

		const reqHtml = doc.is_required
			? `<span style="font-size:10px;background:#fee2e2;color:#991b1b;padding:1px 6px;border-radius:8px;margin-left:5px;">${__("Obrigatório")}</span>`
			: `<span style="font-size:10px;background:#f3f4f6;color:#9ca3af;padding:1px 6px;border-radius:8px;margin-left:5px;">${__("Opcional")}</span>`;

		const fileHtml = doc.file
			? `<a href="${frappe.utils.escape_html(doc.file)}" target="_blank"
				style="font-size:11px;color:#2563eb;text-decoration:underline;">${__("Ver ficheiro")}</a>`
			: "";
		const dateHtml = doc.submitted_date
			? `<span style="font-size:11px;color:#9ca3af;margin-left:6px;">${frappe.datetime.str_to_user(doc.submitted_date)}</span>`
			: "";

		const rowBg = (isPending && doc.is_required) ? "background:#fffbeb;" : "";

		const actionHtml = isPending
			? `<button class="sdoc-btn-deliver" data-row="${frappe.utils.escape_html(doc.name)}"
				style="font-size:11px;background:#2563eb;color:#fff;border:none;padding:4px 12px;border-radius:6px;cursor:pointer;white-space:nowrap;">
				${__("Marcar Entregue")}
			   </button>`
			: `<button class="sdoc-btn-reset" data-row="${frappe.utils.escape_html(doc.name)}"
				style="font-size:11px;background:none;color:#6b7280;border:1px solid #e5e7eb;padding:4px 10px;border-radius:6px;cursor:pointer;white-space:nowrap;">
				${__("Repor")}
			   </button>`;

		return `
		<tr style="border-bottom:1px solid #f1f5f9;${rowBg}">
			<td style="padding:9px 12px;">
				<span style="font-size:13px;font-weight:500;color:#1e293b;">${frappe.utils.escape_html(doc.document_label || doc.document_type)}</span>
				${reqHtml}
			</td>
			<td style="padding:9px 12px;text-align:center;">${statusHtml}</td>
			<td style="padding:9px 12px;">${fileHtml}${dateHtml}</td>
			<td style="padding:9px 12px;text-align:right;">${actionHtml}</td>
		</tr>`;
	}).join("");

	const html = `
	<div style="margin-bottom:6px;display:flex;align-items:center;justify-content:space-between;gap:8px;">
		<div>
			<span style="font-size:13px;font-weight:600;color:#374151;">${__("Documentos registados")}</span>
			${badge}
		</div>
		<button class="sdoc-btn-add btn btn-xs btn-default" style="white-space:nowrap;">
			${__("+ Adicionar Documento")}
		</button>
	</div>
	<div style="overflow-x:auto;border:1px solid #e2e8f0;border-radius:8px;">
		<table style="width:100%;border-collapse:collapse;font-size:13px;">
			<thead>
				<tr style="background:#f8fafc;border-bottom:2px solid #e2e8f0;">
					<th style="padding:8px 12px;text-align:left;font-size:11px;font-weight:600;color:#64748b;text-transform:uppercase;">${__("Documento")}</th>
					<th style="padding:8px 12px;text-align:center;font-size:11px;font-weight:600;color:#64748b;text-transform:uppercase;">${__("Estado")}</th>
					<th style="padding:8px 12px;text-align:left;font-size:11px;font-weight:600;color:#64748b;text-transform:uppercase;">${__("Ficheiro / Data")}</th>
					<th style="padding:8px 12px;"></th>
				</tr>
			</thead>
			<tbody>${rows}</tbody>
		</table>
	</div>`;

	fd.$wrapper.html(html);

	// Event delegation
	fd.$wrapper.off("click.sdoc").on("click.sdoc", ".sdoc-btn-deliver", function () {
		_deliver_doc_dialog(frm, $(this).data("row"));
	}).on("click.sdoc", ".sdoc-btn-reset", function () {
		_reset_doc_confirm(frm, $(this).data("row"));
	}).on("click.sdoc", ".sdoc-btn-add", function () {
		_add_doc_dialog(frm);
	});
}

function _deliver_doc_dialog(frm, row_name) {
	const d = new frappe.ui.Dialog({
		title: __("Marcar Documento como Entregue"),
		fields: [
			{
				fieldname: "file",
				fieldtype: "Attach",
				label: __("Ficheiro (opcional)"),
				description: __("Carregue uma cópia digitalizada, se disponível."),
			},
			{
				fieldname: "notes",
				fieldtype: "Small Text",
				label: __("Observações"),
			},
		],
		primary_action_label: __("Confirmar Entrega"),
		primary_action(values) {
			frappe.call({
				method: "escola.escola.doctype.student.student.mark_document_delivered",
				args: {
					student:  frm.doc.name,
					row_name,
					file_url: values.file || "",
					notes:    values.notes || "",
				},
				freeze: true,
				freeze_message: __("A guardar…"),
				callback() { frm.reload_doc(); },
			});
			d.hide();
		},
	});
	d.show();
}

function _reset_doc_confirm(frm, row_name) {
	frappe.confirm(
		__("Repor o documento para estado Pendente?"),
		() => frappe.call({
			method: "escola.escola.doctype.student.student.reset_document_status",
			args: { student: frm.doc.name, row_name },
			callback() { frm.reload_doc(); },
		})
	);
}

function _add_doc_dialog(frm) {
	const d = new frappe.ui.Dialog({
		title: __("Adicionar Documento"),
		fields: [
			{
				fieldname: "document_type",
				fieldtype: "Link",
				label: __("Tipo de Documento"),
				options: "Tipo de Documento",
				filters: { is_active: 1 },
				reqd: 1,
			},
			{
				fieldname: "status",
				fieldtype: "Select",
				label: __("Estado"),
				options: "Pendente\nEntregue",
				default: "Pendente",
				reqd: 1,
			},
			{
				fieldname: "file",
				fieldtype: "Attach",
				label: __("Ficheiro (opcional)"),
			},
			{
				fieldname: "notes",
				fieldtype: "Small Text",
				label: __("Observações"),
			},
		],
		primary_action_label: __("Adicionar"),
		primary_action(values) {
			frappe.call({
				method: "escola.escola.doctype.student.student.add_student_document",
				args: {
					student:       frm.doc.name,
					document_type: values.document_type,
					status:        values.status,
					file_url:      values.file || "",
					notes:         values.notes || "",
				},
				freeze: true,
				freeze_message: __("A guardar…"),
				callback(r) {
					if (!r.exc) frm.reload_doc();
				},
			});
			d.hide();
		},
	});
	d.show();
}
