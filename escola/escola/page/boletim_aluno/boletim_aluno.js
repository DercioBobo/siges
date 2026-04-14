frappe.pages["boletim-aluno"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent:        wrapper,
		title:         __("Boletim do Aluno"),
		single_column: true,
	});

	_ba_inject_styles();

	// ── Toolbar fields ────────────────────────────────────────────────────────
	const fStudent = page.add_field({
		fieldname: "student",
		fieldtype: "Link",
		options:   "Student",
		label:     __("Aluno"),
		change() {
			if (wrapper._ba._sup) return;
			wrapper._ba.cache = {};
			_ba_clear_term(wrapper);
			_ba_trigger(wrapper);
		},
	});

	const fYear = page.add_field({
		fieldname: "academic_year",
		fieldtype: "Link",
		options:   "Academic Year",
		label:     __("Ano Lectivo"),
		change() {
			if (wrapper._ba._sup) return;
			wrapper._ba.cache = {};
			_ba_clear_term(wrapper);
			_ba_trigger(wrapper);
		},
	});

	const fTerm = page.add_field({
		fieldname: "academic_term",
		fieldtype: "Link",
		options:   "Academic Term",
		label:     __("Período"),
		get_query() {
			const yr = fYear.get_value();
			return yr ? { filters: { academic_year: yr } } : {};
		},
		change() {
			if (wrapper._ba._sup) return;
			_ba_trigger(wrapper, /* use_cache */ true);
		},
	});

	const fView = page.add_field({
		fieldname: "view_mode",
		fieldtype: "Select",
		options:   "Completo\nSó Anual",
		label:     __("Vista"),
		change() {
			if (wrapper._ba._sup) return;
			_ba_trigger(wrapper, true);
		},
	});

	// ── Buttons ───────────────────────────────────────────────────────────────
	page.add_button(__("Limpar"), () => {
		// Suppress all change cascades while resetting
		wrapper._ba._sup = true;
		fTerm.set_value("");
		fYear.set_value("");
		fStudent.set_value("");
		fView.set_value("Completo");
		wrapper._ba._sup = false;
		wrapper._ba.cache = {};
		wrapper._ba.$content.html(_ba_empty_msg());
	});

	page.add_button(__("Imprimir"), () => window.print(), { icon: "printer" });

	// ── IMPORTANT: append a dedicated content div AFTER page.add_field calls.
	// Frappe puts page_form inside page.body, so we must never replace all of
	// page.body — only update this child div.
	const $content = $('<div class="ba-content-area"></div>').appendTo(page.body);
	$content.html(_ba_empty_msg());

	wrapper._ba = {
		page, fStudent, fYear, fTerm, fView,
		$content,
		cache: {},
		_sup: false,   // suppression flag prevents change-event cascades
	};
};

frappe.pages["boletim-aluno"].on_page_show = function (wrapper) {
	const ba = wrapper._ba;
	if (!ba) return;

	const opts = frappe.route_options || {};
	frappe.route_options = {};

	if (opts.student) {
		ba.cache = {};
		_ba_clear_term(wrapper);
		ba.fStudent.set_value(opts.student);
		// set_value triggers fStudent.change() → _ba_trigger
	}
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function _ba_empty_msg() {
	return `<div class="ba-empty">${__("Seleccione um aluno para ver o boletim.")}</div>`;
}

/** Clear the term field without triggering its change handler. */
function _ba_clear_term(wrapper) {
	wrapper._ba._sup = true;
	wrapper._ba.fTerm.set_value("");
	wrapper._ba._sup = false;
}

// ── Orchestration ─────────────────────────────────────────────────────────────

async function _ba_trigger(wrapper, use_cache = false) {
	const ba = wrapper._ba;
	const { $content, fStudent, fYear, fTerm, fView } = ba;

	const student = fStudent.get_value();
	const year    = fYear.get_value()  || "";
	const term    = fTerm.get_value()  || "";
	const view    = fView.get_value()  || "Completo";

	if (!student) {
		$content.html(_ba_empty_msg());
		return;
	}

	const cacheKey = `${student}__${year}`;

	if (use_cache && ba.cache[cacheKey]) {
		_ba_draw($content, ba.cache[cacheKey], term, view);
		return;
	}

	$content.html(
		`<div class="ba-loading"><div class="ba-spinner"></div>${__("A carregar…")}</div>`
	);

	const r = await frappe.call({
		method: "escola.escola.page.boletim_aluno.boletim_aluno.get_student_report",
		args:   { student, academic_year: year },
	});

	if (!r.message) { $content.html(""); return; }
	const data = r.message;

	if (data.error) {
		$content.html(`<div class="ba-empty">${__("Aluno não encontrado.")}</div>`);
		return;
	}
	if (!data.years || !data.years.length) {
		$content.html(
			`<div class="ba-empty">${__("Sem dados académicos para este aluno.")}</div>`
		);
		return;
	}

	ba.cache[cacheKey] = data;
	_ba_draw($content, data, term, view);
}

// ── Draw ──────────────────────────────────────────────────────────────────────

function _ba_draw($content, data, filterTerm, viewMode) {
	const statusColor = {
		"Activo":      "#16a34a",
		"Transferido": "#b45309",
		"Desistente":  "#dc2626",
		"Concluiu":    "#1d4ed8",
	}[data.current_status] || "#6b7280";

	// Student name links to their form
	const studentHref = `/app/student/${encodeURIComponent(data.student)}`;

	let html = `
	<div class="ba-student-header">
		<a class="ba-student-name" href="${studentHref}"
		   title="${__("Abrir ficha do aluno")}" onclick="event.stopPropagation()">
			${frappe.utils.escape_html(data.full_name)}
		</a>
		<div class="ba-student-meta">
			<span class="ba-code">${frappe.utils.escape_html(data.student_code || "")}</span>
			<span class="ba-status-pill" style="background:${statusColor}20;color:${statusColor};">
				${frappe.utils.escape_html(__(data.current_status || ""))}
			</span>
		</div>
	</div>`;

	let yearsRendered = 0;
	for (const yr of data.years) {
		const card = _ba_year_html(yr, filterTerm, viewMode);
		if (card) { html += card; yearsRendered++; }
	}

	if (!yearsRendered) {
		html += `<div class="ba-empty ba-empty-sm">
			${__("Nenhum ano lectivo corresponde aos filtros seleccionados.")}
		</div>`;
	}

	$content.html(html);
}

// ── Year card ─────────────────────────────────────────────────────────────────

function _ba_year_html(yr, filterTerm, viewMode) {
	// Find which column to show (null = show all)
	let termIdx = null;
	if (filterTerm) {
		const idx = (yr.term_names || []).indexOf(filterTerm);
		if (idx === -1) return null; // this year has no such term → skip card
		termIdx = idx;
	}

	// "Só Anual" collapses term columns; ignored when a single term is pinned
	const onlyAnnual = (viewMode === "Só Anual") && termIdx === null;
	const showTerms  = !onlyAnnual;
	const showAnnual = termIdx === null; // single-term view hides annual average

	// ── Column headers ────────────────────────────────────────────────────
	let termHeaders = "";
	if (showTerms) {
		const labels = termIdx !== null ? [yr.term_labels[termIdx]] : yr.term_labels;
		termHeaders = labels.map(t =>
			`<th class="ba-th ba-th-center">${frappe.utils.escape_html(t)}</th>`
		).join("");
	}
	const annualHeader = showAnnual
		? `<th class="ba-th ba-th-center ba-col-annual">${__("Média Anual")}</th>` : "";

	// ── Subject rows ──────────────────────────────────────────────────────
	const subjectRows = yr.subjects.map(s => {
		let termCells = "";
		if (showTerms) {
			const grades = termIdx !== null ? [s.term_grades[termIdx]] : s.term_grades;
			termCells = grades.map(g =>
				`<td class="ba-td ba-td-num">${_ba_fmt(g)}</td>`
			).join("");
		}
		let annualCell = "";
		if (showAnnual) {
			const ann = s.annual_average;
			const cls = ann != null && ann < 10 ? " ba-fail" : "";
			annualCell = `<td class="ba-td ba-td-num ba-col-annual${cls}">${_ba_fmt(ann)}</td>`;
		}
		return `<tr class="ba-row">
			<td class="ba-td ba-td-subj">${frappe.utils.escape_html(s.subject)}</td>
			${termCells}
			${annualCell}
		</tr>`;
	}).join("");

	// ── Average footer ────────────────────────────────────────────────────
	let avgTermCells = "";
	if (showTerms) {
		const avgs = termIdx !== null ? [yr.term_averages[termIdx]] : yr.term_averages;
		avgTermCells = avgs.map(a =>
			`<td class="ba-td ba-td-num ba-avg-cell">${_ba_fmt(a)}</td>`
		).join("");
	}
	let overallCell = "";
	if (showAnnual) {
		const ov  = yr.overall_average;
		const cls = ov != null && ov < 10 ? " ba-fail" : "";
		overallCell = `<td class="ba-td ba-td-num ba-col-annual ba-avg-cell${cls}">${_ba_fmt(ov)}</td>`;
	}

	// ── Decision badge ────────────────────────────────────────────────────
	const DC = {
		"Promovido": { bg: "#d1fae5", color: "#065f46" },
		"Concluído": { bg: "#dbeafe", color: "#1e40af" },
		"Retido":    { bg: "#fee2e2", color: "#991b1b" },
	};
	const dc = DC[yr.final_decision] || { bg: "#f3f4f6", color: "#6b7280" };

	const absText      = yr.total_absences != null
		? `<span class="ba-absences">${yr.total_absences} ${__("falta(s)")}</span>` : "";
	const decisionHtml = yr.final_decision
		? `<span class="ba-decision-badge" style="background:${dc.bg};color:${dc.color};">
			${__(yr.final_decision)}
		   </span>` : "";

	return `
	<div class="ba-year-card">
		<div class="ba-year-header">
			<div class="ba-year-left">
				<span class="ba-year-label">${frappe.utils.escape_html(yr.academic_year)}</span>
				<span class="ba-class-tag">
					${frappe.utils.escape_html(yr.school_class || "")}
					${yr.class_group ? "· " + frappe.utils.escape_html(yr.class_group) : ""}
				</span>
			</div>
			<div class="ba-year-right">
				${absText}
				${decisionHtml}
			</div>
		</div>
		<div class="ba-table-wrap">
			<table class="ba-table">
				<thead>
					<tr>
						<th class="ba-th ba-th-subj">${__("Disciplina")}</th>
						${termHeaders}
						${annualHeader}
					</tr>
				</thead>
				<tbody>${subjectRows}</tbody>
				<tfoot>
					<tr class="ba-avg-row">
						<td class="ba-td ba-td-subj ba-avg-label">${__("Média da Turma")}</td>
						${avgTermCells}
						${overallCell}
					</tr>
				</tfoot>
			</table>
		</div>
	</div>`;
}

function _ba_fmt(v) {
	return v == null ? "—" : v.toFixed(1);
}

// ── Styles ────────────────────────────────────────────────────────────────────

function _ba_inject_styles() {
	if (document.getElementById("ba-styles")) return;
	const s = document.createElement("style");
	s.id = "ba-styles";
	s.textContent = `
/* ── Content area ─────────────────────────────────────────────── */
.ba-content-area {
	padding-top: 16px;
	min-height: 120px;
}

/* ── State ────────────────────────────────────────────────────── */
.ba-empty {
	text-align: center; padding: 80px 20px;
	color: var(--text-muted); font-size: 14px;
}
.ba-empty-sm {
	text-align: center; padding: 30px 20px;
	color: var(--text-muted); font-size: 13px;
}
.ba-loading {
	display: flex; align-items: center; justify-content: center;
	gap: 10px; padding: 80px 20px;
	color: var(--text-muted); font-size: 14px;
}
.ba-spinner {
	width: 18px; height: 18px; border-radius: 50%;
	border: 2px solid var(--border-color);
	border-top-color: var(--primary);
	animation: ba-spin .7s linear infinite;
}
@keyframes ba-spin { to { transform: rotate(360deg); } }

/* ── Student header ───────────────────────────────────────────── */
.ba-student-header {
	padding: 4px 4px 16px;
	border-bottom: 1px solid var(--border-color);
	margin-bottom: 20px;
}
.ba-student-name {
	display: block;
	font-size: 22px; font-weight: 700;
	color: var(--heading-color);
	text-decoration: none;
	margin-bottom: 6px;
}
.ba-student-name:hover { text-decoration: underline; color: var(--primary); }
.ba-student-meta { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.ba-code { font-size: 13px; color: var(--text-muted); font-weight: 500; }
.ba-status-pill {
	font-size: 11px; font-weight: 700;
	padding: 2px 10px; border-radius: 12px;
}

/* ── Year card ────────────────────────────────────────────────── */
.ba-year-card {
	border: 1px solid var(--border-color); border-radius: 12px;
	margin-bottom: 20px; overflow: hidden;
	background: var(--fg-color);
}
.ba-year-header {
	display: flex; align-items: center; justify-content: space-between;
	padding: 14px 18px; flex-wrap: wrap; gap: 8px;
	background: var(--subtle-fg);
	border-bottom: 1px solid var(--border-color);
}
.ba-year-left  { display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap; }
.ba-year-right { display: flex; align-items: center; gap: 10px; }
.ba-year-label { font-size: 16px; font-weight: 700; color: var(--heading-color); }
.ba-class-tag  { font-size: 12px; color: var(--text-muted); }
.ba-absences   { font-size: 12px; color: var(--text-muted); }
.ba-decision-badge {
	font-size: 12px; font-weight: 700;
	padding: 4px 14px; border-radius: 14px;
}

/* ── Table ────────────────────────────────────────────────────── */
.ba-table-wrap { overflow-x: auto; }
.ba-table {
	width: 100%; border-collapse: collapse; font-size: 13px;
}
.ba-th {
	padding: 10px 14px; font-size: 11px; font-weight: 700;
	color: var(--text-muted); text-transform: uppercase;
	letter-spacing: .06em; background: #f8fafc;
	border-bottom: 2px solid var(--border-color);
}
.ba-th-subj   { text-align: left; min-width: 160px; padding-left: 18px; }
.ba-th-center { text-align: center; min-width: 80px; }
.ba-col-annual {
	background: rgba(30,64,175,.04) !important;
	border-left: 2px solid #bfdbfe !important;
	font-weight: 700;
}
.ba-td { padding: 9px 14px; border-bottom: 1px solid var(--border-color); }
.ba-td-subj { padding-left: 18px; font-weight: 500; color: var(--text-color); }
.ba-td-num  { text-align: center; font-variant-numeric: tabular-nums; }
.ba-row:last-child .ba-td { border-bottom: none; }

.ba-fail { color: #dc2626; font-weight: 700; }

/* ── Average footer ───────────────────────────────────────────── */
.ba-avg-row .ba-td {
	border-bottom: none !important;
	border-top: 2px solid #bfdbfe;
	background: linear-gradient(to right, #eff6ff, #f0f9ff);
}
.ba-avg-label {
	font-size: 11px; font-weight: 700; color: #1e40af;
	text-transform: uppercase; letter-spacing: .05em;
}
.ba-avg-cell { color: #1e40af; font-weight: 700; }

/* ── Print ────────────────────────────────────────────────────── */
@media print {
	.page-head, .page-head-content, .page-toolbar, .page-form,
	.layout-side-section, .navbar, .sidebar-toggle-btn,
	.page-actions { display: none !important; }

	.ba-year-card { page-break-inside: avoid; margin-bottom: 12px; }
	.layout-main-section { padding: 0 !important; }

	.ba-student-header { padding: 0 0 12px; }
	.ba-student-name   { font-size: 18px; }
	.ba-table          { font-size: 11px; }
	.ba-th, .ba-td     { padding: 6px 10px; }
	.ba-year-label     { font-size: 14px; }
}
	`;
	document.head.appendChild(s);
}
