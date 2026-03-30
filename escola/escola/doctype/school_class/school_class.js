// Copyright (c) 2024, EntreTech and contributors
// For license information, please see license.txt

frappe.ui.form.on("School Class", {
	refresh(frm) {
		frm.set_query("default_teacher", () => ({
			filters: { is_active: 1 },
		}));

		if (!frm.is_new()) {
			_inject_styles();
			_render_turmas(frm);
		}
	},

	teaching_model(frm) {
		if (frm.doc.teaching_model !== "Professor Único") {
			frm.set_value("default_teacher", null);
		}
	},
});

// ─── Styles ─────────────────────────────────────────────────────────────────

function _inject_styles() {
	if (document.getElementById("escola-sc-styles")) return;
	const s = document.createElement("style");
	s.id = "escola-sc-styles";
	s.textContent = `
		.sc-turmas-header {
			display: flex;
			align-items: center;
			gap: 8px;
			margin-bottom: 14px;
		}
		.sc-turmas-title {
			font-size: 12px;
			font-weight: 700;
			color: var(--text-muted);
			text-transform: uppercase;
			letter-spacing: 0.6px;
		}
		.sc-turmas-count {
			background: var(--bg-blue);
			color: var(--blue-600);
			border-radius: 10px;
			padding: 1px 8px;
			font-size: 11px;
			font-weight: 700;
		}
		.sc-turmas-grid {
			display: grid;
			grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
			gap: 12px;
		}
		.sc-turma-card {
			background: var(--card-bg);
			border: 1px solid var(--border-color);
			border-left-width: 4px;
			border-radius: 8px;
			padding: 14px 16px;
			cursor: pointer;
			transition: box-shadow 0.15s, transform 0.15s;
			display: flex;
			flex-direction: column;
			gap: 4px;
		}
		.sc-turma-card:hover {
			box-shadow: 0 4px 16px rgba(0,0,0,0.10);
			transform: translateY(-2px);
		}
		.sc-turma-card.inactive {
			opacity: 0.55;
		}
		.sc-turma-card-header {
			display: flex;
			align-items: flex-start;
			justify-content: space-between;
			gap: 6px;
			margin-bottom: 2px;
		}
		.sc-turma-name {
			font-size: 15px;
			font-weight: 700;
			color: var(--text-color);
		}
		.sc-turma-badge {
			font-size: 10px;
			font-weight: 700;
			padding: 2px 8px;
			border-radius: 10px;
			white-space: nowrap;
			flex-shrink: 0;
		}
		.sc-turma-badge.active {
			background: var(--green-highlight-color, #dcfce7);
			color: var(--green-600, #16a34a);
		}
		.sc-turma-badge.inactive {
			background: var(--gray-100, #f3f4f6);
			color: var(--gray-500, #6b7280);
		}
		.sc-turma-meta {
			font-size: 12px;
			color: var(--text-muted);
			display: flex;
			align-items: center;
			gap: 5px;
		}
		.sc-turma-footer {
			display: flex;
			align-items: center;
			justify-content: space-between;
			margin-top: 8px;
			padding-top: 8px;
			border-top: 1px solid var(--border-color);
		}
		.sc-turma-students-pill {
			display: flex;
			align-items: center;
			gap: 5px;
			font-size: 12px;
			font-weight: 600;
			color: var(--text-muted);
		}
		.sc-btn-alunos {
			font-size: 11px;
			padding: 4px 12px;
			border-radius: 6px;
			border: 1px solid var(--primary-color);
			color: var(--primary-color);
			background: transparent;
			cursor: pointer;
			font-weight: 600;
			transition: background 0.12s, color 0.12s;
			line-height: 1.4;
		}
		.sc-btn-alunos:hover {
			background: var(--primary-color);
			color: #fff;
		}
		.sc-empty {
			color: var(--text-muted);
			font-size: 13px;
			text-align: center;
			padding: 32px 0;
		}
		/* Students dialog */
		.sc-students-header {
			margin-bottom: 12px;
		}
		.sc-students-summary {
			font-size: 12px;
			color: var(--text-muted);
			margin-bottom: 8px;
		}
		.sc-students-search {
			width: 100%;
			padding: 8px 12px;
			border: 1px solid var(--border-color);
			border-radius: 6px;
			font-size: 13px;
			background: var(--control-bg);
			color: var(--text-color);
			outline: none;
			box-sizing: border-box;
		}
		.sc-students-search:focus {
			border-color: var(--primary-color);
		}
		.sc-students-grid {
			display: grid;
			grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
			gap: 8px;
			max-height: 400px;
			overflow-y: auto;
			margin-top: 12px;
			padding-right: 2px;
		}
		.sc-student-card {
			display: flex;
			align-items: center;
			gap: 10px;
			padding: 10px 12px;
			background: var(--card-bg);
			border: 1px solid var(--border-color);
			border-radius: 8px;
			cursor: pointer;
			transition: box-shadow 0.12s, border-color 0.12s;
		}
		.sc-student-card:hover {
			box-shadow: 0 2px 8px rgba(0,0,0,0.08);
			border-color: var(--primary-color);
		}
		.sc-student-avatar {
			width: 36px;
			height: 36px;
			border-radius: 50%;
			display: flex;
			align-items: center;
			justify-content: center;
			font-size: 12px;
			font-weight: 700;
			color: #fff;
			flex-shrink: 0;
		}
		.sc-student-name {
			font-size: 12px;
			font-weight: 500;
			color: var(--text-color);
			line-height: 1.3;
			overflow: hidden;
			display: -webkit-box;
			-webkit-line-clamp: 2;
			-webkit-box-orient: vertical;
		}
		.sc-no-results {
			grid-column: 1 / -1;
			text-align: center;
			color: var(--text-muted);
			font-size: 13px;
			padding: 24px 0;
		}
	`;
	document.head.appendChild(s);
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

const _PALETTE = [
	"#4f9cf9", "#7c6df0", "#f97316", "#22c55e",
	"#ec4899", "#06b6d4", "#a855f7", "#eab308",
	"#ef4444", "#14b8a6",
];

function _color(str) {
	str = str || "?";
	let h = 0;
	for (let i = 0; i < str.length; i++) h = (h * 31 + str.charCodeAt(i)) & 0xffff;
	return _PALETTE[h % _PALETTE.length];
}

function _initials(name) {
	return (name || "?").trim().split(/\s+/).slice(0, 2).map(w => w[0].toUpperCase()).join("");
}

// ─── Turma cards ─────────────────────────────────────────────────────────────

async function _render_turmas(frm) {
	const $wrap = frm.get_field("turmas_html").$wrapper;
	$wrap.html(`<div class="sc-empty text-muted">${__("A carregar turmas…")}</div>`);

	const r = await frappe.call({
		method: "escola.escola.doctype.school_class.school_class.get_turmas_summary",
		args: { school_class: frm.doc.name },
	});

	const groups = r.message || [];

	if (!groups.length) {
		$wrap.html(`<div class="sc-empty">${__("Nenhuma turma encontrada para esta classe.")}</div>`);
		return;
	}

	const cardsHtml = groups.map(g => {
		const accent = _color(g.name);
		const badgeClass = g.is_active ? "active" : "inactive";
		const badgeLabel = g.is_active ? __("Activa") : __("Inactiva");
		const teacherLine = g.teacher_name
			? `<div class="sc-turma-meta">👤 ${frappe.utils.escape_html(g.teacher_name)}</div>`
			: `<div class="sc-turma-meta" style="opacity:0.5">${__("Sem professor titular")}</div>`;

		return `
			<div class="sc-turma-card ${g.is_active ? "" : "inactive"}"
				 data-name="${frappe.utils.escape_html(g.name)}"
				 style="border-left-color:${accent}">
				<div class="sc-turma-card-header">
					<div class="sc-turma-name">${frappe.utils.escape_html(g.name)}</div>
					<div class="sc-turma-badge ${badgeClass}">${badgeLabel}</div>
				</div>
				<div class="sc-turma-meta">📅 ${frappe.utils.escape_html(g.academic_year || "—")}</div>
				${teacherLine}
				<div class="sc-turma-footer">
					<div class="sc-turma-students-pill">
						<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
							<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
							<circle cx="9" cy="7" r="4"/>
							<path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>
						</svg>
						${g.student_count}
					</div>
					<button class="sc-btn-alunos" data-group="${frappe.utils.escape_html(g.name)}">
						${__("Ver Alunos")} →
					</button>
				</div>
			</div>`;
	}).join("");

	$wrap.html(`
		<div class="sc-turmas-header">
			<span class="sc-turmas-title">${__("Turmas")}</span>
			<span class="sc-turmas-count">${groups.length}</span>
		</div>
		<div class="sc-turmas-grid">${cardsHtml}</div>
	`);

	$wrap.find(".sc-turma-card").on("click", function (e) {
		if ($(e.target).closest(".sc-btn-alunos").length) return;
		frappe.set_route("Form", "Class Group", $(this).data("name"));
	});

	$wrap.find(".sc-btn-alunos").on("click", function (e) {
		e.stopPropagation();
		_show_students_dialog($(this).data("group"));
	});
}

// ─── Students dialog ─────────────────────────────────────────────────────────

async function _show_students_dialog(class_group) {
	const dlg = new frappe.ui.Dialog({
		title: __("Alunos — {0}", [class_group]),
		size: "large",
	});

	dlg.$body.html(
		`<div class="sc-empty text-muted">${__("A carregar alunos…")}</div>`
	);
	dlg.show();

	const students = await frappe.db.get_list("Class Group Student", {
		filters: { parent: class_group },
		fields: ["student", "student_name"],
		order_by: "student_name asc",
		limit: 500,
	});

	if (!students.length) {
		dlg.$body.html(`<div class="sc-empty">${__("Esta turma não tem alunos.")}</div>`);
		return;
	}

	const cardsHtml = students.map(s => {
		const name = s.student_name || s.student;
		const color = _color(s.student);
		const ini = _initials(name);
		return `
			<div class="sc-student-card" data-student="${frappe.utils.escape_html(s.student)}">
				<div class="sc-student-avatar" style="background:${color}">${ini}</div>
				<div class="sc-student-name">${frappe.utils.escape_html(name)}</div>
			</div>`;
	}).join("");

	dlg.$body.html(`
		<div class="sc-students-header">
			<div class="sc-students-summary">${__("{0} aluno(s) nesta turma", [students.length])}</div>
			<input class="sc-students-search" type="text" placeholder="${__("Pesquisar aluno…")}" />
		</div>
		<div class="sc-students-grid">${cardsHtml}</div>
	`);

	dlg.$body.find(".sc-students-search").on("input", function () {
		const q = this.value.toLowerCase();
		let visible = 0;
		dlg.$body.find(".sc-student-card").each(function () {
			const match = $(this).find(".sc-student-name").text().toLowerCase().includes(q);
			$(this).toggle(match);
			if (match) visible++;
		});

		dlg.$body.find(".sc-no-results").remove();
		if (!visible) {
			dlg.$body.find(".sc-students-grid").append(
				`<div class="sc-no-results">${__("Nenhum aluno encontrado.")}</div>`
			);
		}
	});

	dlg.$body.find(".sc-student-card").on("click", function () {
		frappe.set_route("Form", "Student", $(this).data("student"));
		dlg.hide();
	});
}
