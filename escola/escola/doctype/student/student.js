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
			_render_action_panel(frm);
			_load_academic_history(frm);
		}
	},

	first_name(frm)    { update_full_name(frm); },
	last_name(frm)     { update_full_name(frm); },
	date_of_birth(frm) { update_age(frm); },
});

// ---------------------------------------------------------------------------
// Styles (injected once)
// ---------------------------------------------------------------------------

function _inject_student_styles() {
	if (document.getElementById("escola-student-styles")) return;
	const s = document.createElement("style");
	s.id = "escola-student-styles";
	s.textContent = `
.stu-panel { margin: 6px 0 4px; }

.stu-group-label {
	font-size: 10px; font-weight: 700; text-transform: uppercase;
	letter-spacing: .7px; color: var(--text-muted); margin-bottom: 6px;
}

.stu-btn-row { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 10px; }

.stu-btn {
	display: inline-flex; align-items: center; gap: 6px;
	padding: 6px 13px; border-radius: 20px; border: 1.5px solid transparent;
	font-size: 12px; font-weight: 600; cursor: pointer;
	transition: filter .15s, transform .12s, box-shadow .12s;
	white-space: nowrap; line-height: 1.3;
	font-family: var(--font-stack);
}
.stu-btn:hover { filter: brightness(.93); transform: translateY(-1px); box-shadow: 0 2px 6px rgba(0,0,0,.1); }
.stu-btn:active { transform: translateY(0); box-shadow: none; }

.stu-btn .stu-ico { font-size: 14px; line-height: 1; }

/* nav variant — outlined pills */
.stu-nav { background: transparent; }

/* action variant — filled pills */
.stu-act { }

/* timeline button */
.stu-timeline-btn {
	display: inline-flex; align-items: center; gap: 8px;
	padding: 8px 16px; border-radius: 8px;
	background: linear-gradient(135deg, #6366f1, #8b5cf6);
	color: #fff; font-size: 13px; font-weight: 600;
	border: none; cursor: pointer;
	transition: opacity .15s, transform .12s, box-shadow .12s;
	font-family: var(--font-stack);
}
.stu-timeline-btn:hover { opacity: .88; transform: translateY(-1px); box-shadow: 0 3px 8px rgba(99,102,241,.35); }

/* ── Timeline modal ──────────────────────────── */
.stl-wrap { padding: 8px 0 4px; }
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
.stl-status-badge {
	font-size: 11px; font-weight: 600; padding: 2px 9px; border-radius: 12px;
	margin-left: 8px;
}
.stl-result { font-weight: 700; font-size: 13px; }
.stl-body { padding: 10px 14px; display: flex; gap: 22px; flex-wrap: wrap; }
.stl-stat { }
.stl-stat-label {
	font-size: 10px; color: var(--text-muted); text-transform: uppercase;
	letter-spacing: .06em; margin-bottom: 2px;
}
.stl-stat-val { font-size: 13px; font-weight: 500; }
.stl-foot {
	padding: 7px 14px; border-top: 1px solid var(--border-color);
	background: var(--subtle-fg); display: flex; gap: 16px; flex-wrap: wrap;
}
.stl-foot a { font-size: 12px; color: #6366f1; text-decoration: none; }
.stl-foot a:hover { text-decoration: underline; }
.stl-empty { text-align: center; padding: 40px 16px; color: var(--text-muted); font-size: 13px; }
	`;
	document.head.appendChild(s);
}

// ---------------------------------------------------------------------------
// Action panel
// ---------------------------------------------------------------------------

function _render_action_panel(frm) {
	_inject_student_styles();
	const fd = frm.fields_dict["student_actions_html"];
	if (!fd) return;

	const status    = frm.doc.current_status;
	const isActive  = !status || status === "Activo";
	const isInactive = status === "Transferido" || status === "Desistente";

	// Navigation links ─────────────────────────────────────────────────────
	const nav = [
		{ id: "boletins",       ico: "📋", label: __("Boletins"),      color: "#4f46e5", bg: "#eef2ff" },
		{ id: "alocacoes",      ico: "📌", label: __("Alocações"),      color: "#0284c7", bg: "#e0f2fe" },
		{ id: "transferencias", ico: "✈", label: __("Transferências"),  color: "#b45309", bg: "#fef3c7" },
		{ id: "facturas",       ico: "🧾", label: __("Facturas"),        color: "#059669", bg: "#d1fae5" },
	];

	// Action buttons ───────────────────────────────────────────────────────
	const actions = [
		{ id: "atribuir-turma",    ico: "＋", label: __("Atribuir Turma"),              color: "#fff", bg: "#2563eb", show: true },
		{ id: "troca-turma",       ico: "⇄",  label: __("Trocar de Turma"),             color: "#fff", bg: "#7c3aed", show: isActive },
		{ id: "transferencia",     ico: "↗",  label: __("Registar Transferência"),      color: "#fff", bg: "#ea580c", show: isActive },
		{ id: "estado-financeiro", ico: "↻",  label: __("Actualizar Estado Financeiro"), color: "#374151", bg: "#f3f4f6", show: true },
		{ id: "reactivar",         ico: "↺",  label: __("Reactivar Aluno"),             color: "#fff", bg: "#16a34a", show: isInactive },
	].filter(b => b.show);

	const navHtml = nav.map(b =>
		`<button class="stu-btn stu-nav" data-action="${b.id}"
		         style="color:${b.color};border-color:${b.color};background:${b.bg}20;">
		     <span class="stu-ico">${b.ico}</span>${b.label}
		 </button>`
	).join("");

	const actHtml = actions.map(b =>
		`<button class="stu-btn stu-act" data-action="${b.id}"
		         style="color:${b.color};background:${b.bg};border-color:${b.bg};">
		     <span class="stu-ico">${b.ico}</span>${b.label}
		 </button>`
	).join("");

	fd.$wrapper.html(`
		<div class="stu-panel">
			<div class="stu-group-label">${__("Ver")}</div>
			<div class="stu-btn-row">
				${navHtml}
				<button class="stu-timeline-btn" data-action="historial">
					<span>🕐</span> ${__("Ver Historial")}
				</button>
			</div>
			<div class="stu-group-label">${__("Acções")}</div>
			<div class="stu-btn-row">${actHtml}</div>
		</div>
	`);

	fd.$wrapper.find("[data-action]").on("click", function () {
		const a = $(this).data("action");
		switch (a) {
			case "boletins":          frappe.set_route("List", "Report Card", { student: frm.doc.name }); break;
			case "alocacoes":         frappe.set_route("List", "Student Group Assignment", { student: frm.doc.name }); break;
			case "transferencias":    frappe.set_route("List", "Student Transfer", { student: frm.doc.name }); break;
			case "facturas":          frappe.set_route("List", "Sales Invoice", { escola_student: frm.doc.name }); break;
			case "historial":         _show_timeline_modal(frm); break;
			case "atribuir-turma":    _assign_class_group_dialog(frm); break;
			case "troca-turma":       frappe.new_doc("Troca de Turma", { student: frm.doc.name }); break;
			case "transferencia":     frappe.new_doc("Student Transfer", { student: frm.doc.name }); break;
			case "estado-financeiro": _update_financial_status(frm); break;
			case "reactivar":         reactivate_dialog(frm); break;
		}
	});
}

// ---------------------------------------------------------------------------
// Assign class group dialog
// ---------------------------------------------------------------------------

function _assign_class_group_dialog(frm) {
	const d = new frappe.ui.Dialog({
		title: __("Atribuir Turma · {0}", [frm.doc.full_name]),
		fields: [
			{
				fieldname: "academic_year",
				fieldtype: "Link",
				options:   "Academic Year",
				label:     __("Ano Lectivo"),
				reqd:      1,
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
// Reactivation dialog (existing, unchanged)
// ---------------------------------------------------------------------------

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
