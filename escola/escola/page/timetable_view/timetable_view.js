// Horário de Turmas — Timetable View Page
// escola/escola/page/timetable_view/timetable_view.js

frappe.pages["timetable-view"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Horário de Turmas"),
		single_column: true,
	});

	new TimetablePage(page, wrapper);
};

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const PALETTE = [
	"#6366F1","#10B981","#F59E0B","#EF4444","#8B5CF6",
	"#EC4899","#14B8A6","#F97316","#0EA5E9","#84CC16",
	"#A855F7","#06B6D4","#D97706","#059669","#7C3AED",
];

const DAY_ABBREV = {
	"Segunda-Feira": "2ª Feira",
	"Terça-Feira":   "3ª Feira",
	"Quarta-Feira":  "4ª Feira",
	"Quinta-Feira":  "5ª Feira",
	"Sexta-Feira":   "6ª Feira",
};

// ---------------------------------------------------------------------------
// Main class
// ---------------------------------------------------------------------------

class TimetablePage {
	constructor(page, wrapper) {
		this.page    = page;
		this.wrapper = wrapper;
		this._palette_idx = 0;
		this._color_cache = {};

		this._build_skeleton();
		this._add_page_actions();
		this._load_filter_options();
	}

	// -----------------------------------------------------------------------
	// Setup
	// -----------------------------------------------------------------------

	_build_skeleton() {
		const $body = $(this.wrapper).find(".page-content");
		$body.empty();

		this.$root = $(`
			<div class="tt-page" style="padding:0 20px 40px;">
				<div class="tt-filters" style="padding:18px 0 8px;"></div>
				<div class="tt-content" style="margin-top:8px;"></div>
			</div>
		`).appendTo($body);

		this.$filters = this.$root.find(".tt-filters");
		this.$content = this.$root.find(".tt-content");

		// Print styles (injected once)
		if (!document.getElementById("tt-print-styles")) {
			const style = document.createElement("style");
			style.id = "tt-print-styles";
			style.textContent = `
				@media print {
					.navbar, .page-head, .page-actions, .tt-filters,
					.btn, .sidebar-toggle-btn { display:none !important; }
					.tt-page { padding:0 !important; }
					.tt-grid td, .tt-grid th { border:1px solid #ccc !important; }
				}
			`;
			document.head.appendChild(style);
		}
	}

	_add_page_actions() {
		this.page.add_button(__("Imprimir"), () => window.print(), { icon: "fa fa-print" });
		this.page.add_button(__("Novo Horário"), () => frappe.new_doc("Timetable"),
			{ icon: "fa fa-plus" });
	}

	// -----------------------------------------------------------------------
	// Filter bar
	// -----------------------------------------------------------------------

	_load_filter_options() {
		frappe.call({
			method: "escola.escola.page.timetable_view.timetable_view.get_filter_options",
			callback: (r) => {
				if (!r.message) return;
				this._opts = r.message;
				this._render_filters(r.message);
			},
		});
	}

	_render_filters(opts) {
		const years   = opts.years        || [];
		const classes = opts.class_groups || [];

		const year_opts = years.map(
			y => `<option value="${y.name}">${y.year_name || y.name}</option>`
		).join("");

		const cg_opts = classes.map(
			c => `<option value="${c.name}" data-shift="${c.shift || ''}">`
				 + `${c.group_name}${c.shift ? " · " + c.shift : ""}</option>`
		).join("");

		this.$filters.html(`
			<div style="display:flex;gap:12px;align-items:flex-end;flex-wrap:wrap;">
				<div>
					<label class="tt-label">ANO LECTIVO</label>
					<select id="tt-year" class="form-control" style="min-width:200px;">
						<option value="">— Selecione o Ano —</option>
						${year_opts}
					</select>
				</div>
				<div>
					<label class="tt-label">TURMA</label>
					<select id="tt-cg" class="form-control" style="min-width:200px;">
						<option value="">— Selecione a Turma —</option>
						${cg_opts}
					</select>
				</div>
			</div>
			<style>
				.tt-label { font-size:11px; color:#6B7280; font-weight:700;
				            display:block; margin-bottom:4px; letter-spacing:.5px; }
			</style>
		`);

		// Auto-select current academic year from School Settings
		frappe.db.get_single_value("School Settings", "current_academic_year").then(val => {
			if (val) this.$filters.find("#tt-year").val(val);
		});

		// Auto-load timetable when turma is selected
		this.$filters.find("#tt-cg").on("change", () => this._load_timetable());
		// Also reload if year changes after a turma is already selected
		this.$filters.find("#tt-year").on("change", () => {
			if (this.$filters.find("#tt-cg").val()) this._load_timetable();
		});
	}

	// -----------------------------------------------------------------------
	// Data loading
	// -----------------------------------------------------------------------

	_load_timetable() {
		const year = this.$filters.find("#tt-year").val();
		const cg   = this.$filters.find("#tt-cg").val();

		if (!year || !cg) {
			frappe.msgprint(__("Selecione o Ano Lectivo e a Turma."));
			return;
		}

		this.$content.html(`
			<div style="text-align:center;padding:60px;color:#9CA3AF;">
				<i class="fa fa-spinner fa-spin fa-2x"></i>
				<div style="margin-top:12px;font-size:14px;">A carregar horário…</div>
			</div>
		`);

		frappe.call({
			method: "escola.escola.page.timetable_view.timetable_view.get_timetable_data",
			args: { class_group: cg, academic_year: year },
			callback: (r) => {
				if (r.exc) return;
				this._render(r.message);
			},
		});
	}

	// -----------------------------------------------------------------------
	// Rendering
	// -----------------------------------------------------------------------

	_render(data) {
		if (!data) return;

		this._palette_idx = 0;
		this._color_cache = {};

		// Pre-build color map from summary (consistent palette index)
		(data.subjects_summary || []).forEach(s => {
			this._subject_color(s.subject_code, s.color);
		});

		if (!data.found) {
			this._render_empty(data.class_group_info);
			return;
		}

		const html = [
			this._html_info_bar(data),
			this._html_grid(data),
			this._html_legend(data.subjects_summary),
		].join("");

		this.$content.html(html);
	}

	_render_empty(cg) {
		const name = cg ? cg.group_name : __("esta turma");
		this.$content.html(`
			<div style="text-align:center;padding:70px 20px;background:#F9FAFB;
			            border-radius:12px;margin-top:8px;border:1px dashed #E5E7EB;">
				<i class="fa fa-calendar-o fa-3x" style="color:#D1D5DB;"></i>
				<h3 style="color:#374151;margin-top:16px;font-weight:700;">
					Sem horário activo
				</h3>
				<p style="color:#6B7280;margin:8px 0 20px;">
					Não existe um horário activo para <b>${frappe.utils.escape_html(name)}</b>
					neste período.
				</p>
				<button class="btn btn-primary btn-sm" onclick="frappe.new_doc('Timetable')">
					<i class="fa fa-plus"></i>&nbsp;Criar Horário
				</button>
			</div>
		`);
	}

	_html_info_bar(data) {
		const cg            = data.class_group_info || {};
		const shift_color   = cg.shift === "Tarde" ? "#F59E0B" : "#6366F1";
		const teacher_block = cg.teacher_name
			? `<div style="border-left:1px solid #E5E7EB;padding-left:20px;">
				<div style="font-size:11px;color:#9CA3AF;font-weight:700;">PROFESSOR TITULAR</div>
				<div style="font-size:14px;font-weight:600;color:#374151;">${frappe.utils.escape_html(cg.teacher_name)}</div>
			   </div>`
			: "";
		const shift_block = cg.shift
			? `<div>
				<span style="padding:5px 14px;border-radius:20px;font-size:12px;font-weight:700;
				             background:${shift_color}1A;color:${shift_color};">
					${cg.shift}
				</span>
			   </div>`
			: "";

		return `
			<div style="background:white;border:1px solid #E5E7EB;border-radius:10px;
			            padding:16px 20px;margin-bottom:14px;display:flex;gap:20px;
			            flex-wrap:wrap;align-items:center;">
				<div>
					<div style="font-size:11px;color:#9CA3AF;font-weight:700;">TURMA</div>
					<div style="font-size:20px;font-weight:800;color:#111827;">
						${frappe.utils.escape_html(cg.group_name || "")}
					</div>
				</div>
				${teacher_block}
				${shift_block}
				<div style="margin-left:auto;">
					<a href="/app/timetable/${encodeURIComponent(data.timetable_name)}"
					   class="btn btn-default btn-xs" target="_blank">
						<i class="fa fa-pencil"></i>&nbsp;Editar Horário
					</a>
				</div>
			</div>
		`;
	}

	_html_grid(data) {
		const { time_slots, days, grid } = data;
		if (!time_slots || !time_slots.length) {
			return `<div style="color:#9CA3AF;padding:20px;text-align:center;">
				Sem slots de horário configurados para este turno.
			</div>`;
		}

		const col_pct = Math.floor(82 / days.length);
		const header_cells = days.map(d =>
			`<th style="background:#1E293B;color:white;border-radius:6px;
			            padding:10px 6px;font-size:12px;font-weight:700;
			            text-align:center;width:${col_pct}%;">
				${DAY_ABBREV[d] || d}
			</th>`
		).join("");

		const rows = time_slots.map(slot => this._html_row(slot, days, grid)).join("");

		return `
			<div style="overflow-x:auto;-webkit-overflow-scrolling:touch;">
			<table class="tt-grid" style="width:100%;border-collapse:separate;
			                              border-spacing:3px;table-layout:fixed;">
				<thead>
					<tr>
						<th style="width:10%;min-width:82px;background:#F3F4F6;
						           border-radius:6px;padding:10px 6px;font-size:11px;
						           color:#6B7280;font-weight:700;text-align:center;">
							HORÁRIO
						</th>
						${header_cells}
					</tr>
				</thead>
				<tbody>${rows}</tbody>
			</table>
			</div>
		`;
	}

	_html_row(slot, days, grid) {
		const is_break = slot.slot_type === "Intervalo" || slot.slot_type === "Borla";

		const time_cell = `
			<td style="background:#F3F4F6;border-radius:6px;padding:7px 5px;
			           text-align:center;vertical-align:middle;">
				<div style="font-size:11px;font-weight:700;color:#374151;">
					${frappe.utils.escape_html(slot.label)}
				</div>
			</td>
		`;

		if (is_break) {
			const label = slot.slot_type === "Intervalo" ? "— INTERVALO —" : "— BORLA —";
			return `<tr>
				${time_cell}
				<td colspan="${days.length}"
				    style="background:#F1F5F9;border-radius:6px;padding:7px 12px;
				           font-size:11px;color:#94A3B8;font-weight:700;
				           text-align:center;letter-spacing:2px;">
					${label}
				</td>
			</tr>`;
		}

		const day_cells = days.map(day => {
			const cell = (grid[day] || {})[slot.name];
			if (!cell || !cell.subject_code) {
				return `<td style="background:#F9FAFB;border-radius:6px;min-height:56px;"></td>`;
			}
			return this._html_cell(cell);
		}).join("");

		return `<tr>${time_cell}${day_cells}</tr>`;
	}

	_html_cell(cell) {
		const color = this._subject_color(cell.subject_code, cell.color);

		return `
			<td style="background:white;border-radius:6px;padding:5px 3px;vertical-align:middle;">
				<div style="background:${color}1A;border-left:3px solid ${color};
				            border-radius:4px;padding:6px 8px;min-height:54px;">
					<div style="font-size:13px;font-weight:800;color:${color};
					            letter-spacing:.5px;">
						${frappe.utils.escape_html(cell.subject_code)}
					</div>
					<div style="font-size:10px;color:#6B7280;margin-top:2px;line-height:1.3;">
						${frappe.utils.escape_html(cell.teacher || "")}
					</div>
				</div>
			</td>
		`;
	}

	_html_legend(summary) {
		if (!summary || !summary.length) return "";

		const badges = summary.map(s => {
			const color = this._subject_color(s.subject_code, s.color);
			return `
				<div style="display:flex;align-items:center;gap:6px;background:#F9FAFB;
				            border-radius:6px;padding:6px 10px;">
					<div style="width:12px;height:12px;background:${color};border-radius:3px;"></div>
					<span style="font-size:12px;font-weight:800;color:${color};">
						${frappe.utils.escape_html(s.subject_code)}
					</span>
					<span style="font-size:12px;color:#374151;">
						${frappe.utils.escape_html(s.subject)}
					</span>
					<span style="font-size:11px;color:#9CA3AF;">
						(${s.slots} aula${s.slots !== 1 ? "s" : ""}/sem.)
					</span>
				</div>
			`;
		}).join("");

		return `
			<div style="margin-top:18px;background:white;border:1px solid #E5E7EB;
			            border-radius:10px;padding:16px 20px;">
				<div style="font-size:11px;color:#9CA3AF;font-weight:700;
				            margin-bottom:10px;letter-spacing:1px;">
					LEGENDA
				</div>
				<div style="display:flex;flex-wrap:wrap;gap:8px;">${badges}</div>
			</div>
		`;
	}

	// -----------------------------------------------------------------------
	// Color helper  (uses subject.color if set, else cycles the palette)
	// -----------------------------------------------------------------------

	_subject_color(code, server_color) {
		if (this._color_cache[code]) return this._color_cache[code];
		const color = (server_color && server_color.trim())
			? server_color.trim()
			: PALETTE[this._palette_idx++ % PALETTE.length];
		this._color_cache[code] = color;
		return color;
	}
}
