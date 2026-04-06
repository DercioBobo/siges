frappe.pages["schedule-monitor"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Monitor de Agendamentos"),
		single_column: true,
	});
	new ScheduleMonitor(page);
};

class ScheduleMonitor {
	constructor(page) {
		this.page  = page;
		this.$body = $(page.body);
		this._build();
	}

	_build() {
		_sm_styles();

		this.page.add_button(__("Actualizar"), () => this.load(), { icon: "refresh" });
		this.page.add_button(__("Novo Agendamento"), () => frappe.new_doc("Billing Schedule"));

		this.$body.html(`
		<div class="sm-wrap">
			<div class="sm-sec-title">${__("Agendamentos Activos")}</div>
			<div class="sm-grid" id="sm-active"></div>

			<div id="sm-inactive-sec" style="display:none">
				<div class="sm-sec-title sm-sec-title--muted">${__("Inactivos")}</div>
				<div id="sm-inactive"></div>
			</div>

			<div id="sm-tl-sec" style="display:none">
				<div class="sm-sec-title">${__("Próximas Execuções — 30 dias")}</div>
				<div id="sm-timeline"></div>
			</div>
		</div>`);

		this.load();
	}

	async load() {
		this.$body.find("#sm-active").html(`<div class="sm-loading">${__("A carregar…")}</div>`);
		const r = await frappe.call({
			method: "escola.escola.page.schedule_monitor.schedule_monitor.get_schedule_data",
		});
		if (r && r.exc) {
			this.$body.find("#sm-active").html(
				`<div class="sm-empty" style="color:var(--red-500);">
					${__("Erro ao carregar dados. Verifique o registo de erros do servidor.")}
				</div>`
			);
			return;
		}
		if (r && r.message) this._render(r.message);
	}

	_render({ schedules, upcoming }) {
		const active   = schedules.filter(s =>  s.is_active);
		const inactive = schedules.filter(s => !s.is_active);

		const MODE_CLS = {
			"Mensal":     "sm-mode--blue",
			"Trimestral": "sm-mode--purple",
			"Anual":      "sm-mode--teal",
		};

		// ── Active cards ──────────────────────────────────────────
		const $grid = this.$body.find("#sm-active").empty();

		if (!active.length) {
			$grid.html(`<div class="sm-empty">${__("Nenhum agendamento activo. Crie um para começar.")}</div>`);
		} else {
			active.forEach(s => {
				const next = s.next_due_date ? frappe.datetime.str_to_user(s.next_due_date) : __("N/D");
				const last = s.last_billed_date ? frappe.datetime.str_to_user(s.last_billed_date) : __("Nunca");
				const warn = s.is_overdue
					? `<span class="sm-warn">${__("⚠ Pendente")}</span>` : "";

				$grid.append(`
				<div class="sm-card" data-name="${frappe.utils.escape_html(s.name)}">
					<div class="sm-card-top">
						<span class="sm-card-name">${frappe.utils.escape_html(s.schedule_name)}</span>
						<span class="sm-mode ${MODE_CLS[s.billing_mode] || ""}">${s.billing_mode}</span>
						${warn}
					</div>
					<div class="sm-card-cls">${frappe.utils.escape_html(s.school_class)}</div>
					<div class="sm-next ${s.is_overdue ? "sm-next--warn" : ""}">
						<div class="sm-next-lbl">${__("Próxima emissão")}</div>
						<div class="sm-next-val">${next}</div>
					</div>
					<div class="sm-rows">
						<div class="sm-row">
							<span>${__("Última emissão:")}</span>
							<span>${last}</span>
						</div>
						<div class="sm-row">
							<span>${__("Alunos activos:")}</span>
							<span>${s.student_count}</span>
						</div>
						<div class="sm-row">
							<span>${__("Valor esperado:")}</span>
							<span>${format_currency(s.expected_total)}</span>
						</div>
					</div>
				</div>`);
			});

			$grid.on("click", ".sm-card", function () {
				frappe.set_route("Form", "Billing Schedule", $(this).data("name"));
			});
		}

		// ── Inactive list ─────────────────────────────────────────
		if (inactive.length) {
			const $il = this.$body.find("#sm-inactive").empty();
			inactive.forEach(s => {
				$il.append(`
				<div class="sm-irow" onclick="frappe.set_route('Form','Billing Schedule','${frappe.utils.escape_html(s.name)}')">
					<span class="sm-iname">${frappe.utils.escape_html(s.schedule_name)}</span>
					<span class="sm-icls">${frappe.utils.escape_html(s.school_class)}</span>
					<span class="sm-imode">${s.billing_mode}</span>
				</div>`);
			});
			this.$body.find("#sm-inactive-sec").show();
		} else {
			this.$body.find("#sm-inactive-sec").hide();
		}

		// ── Timeline ──────────────────────────────────────────────
		if (upcoming.length) {
			const $tl = this.$body.find("#sm-timeline").empty();
			upcoming.forEach(day => {
				const entries = day.entries.map(e =>
					`<span class="sm-tl-chip">
						${frappe.utils.escape_html(e.school_class)}
						· ${e.student_count} ${__("alunos")}
						· ${format_currency(e.expected_total)}
					</span>`
				).join("");
				$tl.append(`
				<div class="sm-tl-row">
					<div class="sm-tl-date">${frappe.datetime.str_to_user(day.date)}</div>
					<div class="sm-tl-chips">${entries}</div>
				</div>`);
			});
			this.$body.find("#sm-tl-sec").show();
		} else {
			this.$body.find("#sm-tl-sec").hide();
		}
	}
}

function _sm_styles() {
	if (document.getElementById("sm-css")) return;
	const s = document.createElement("style");
	s.id = "sm-css";
	s.textContent = `
.sm-wrap { padding: 16px 20px; }
.sm-sec-title { font-size: 12px; font-weight: 700; text-transform: uppercase;
	letter-spacing: .6px; color: var(--text-color); margin: 22px 0 12px; }
.sm-sec-title--muted { color: var(--text-muted); }

/* Cards */
.sm-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); gap: 14px; }
.sm-card { background: var(--fg-color); border: 1.5px solid var(--border-color);
	border-radius: 12px; padding: 16px; cursor: pointer;
	transition: box-shadow .18s, border-color .18s; }
.sm-card:hover { border-color: var(--primary); box-shadow: 0 2px 12px rgba(0,0,0,.07); }
.sm-card-top { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; margin-bottom: 3px; }
.sm-card-name { font-size: 14px; font-weight: 700; flex: 1; min-width: 0;
	white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.sm-mode { font-size: 10px; font-weight: 700; padding: 2px 8px; border-radius: 10px; flex-shrink: 0; }
.sm-mode--blue   { background: #dbeafe; color: #1d4ed8; }
.sm-mode--purple { background: #ede9fe; color: #6d28d9; }
.sm-mode--teal   { background: #ccfbf1; color: #0d9488; }
.sm-warn { font-size: 10px; font-weight: 700; padding: 2px 8px; border-radius: 10px;
	background: #fef3c7; color: #b45309; flex-shrink: 0; }
.sm-card-cls { font-size: 12px; color: var(--text-muted); margin-bottom: 12px; }
.sm-next { background: var(--subtle-fg); border-radius: 8px; padding: 10px 12px; margin-bottom: 10px; }
.sm-next--warn { background: #fef3c7; }
.sm-next-lbl { font-size: 10px; font-weight: 600; text-transform: uppercase;
	letter-spacing: .5px; color: var(--text-muted); margin-bottom: 2px; }
.sm-next-val { font-size: 16px; font-weight: 700; color: var(--text-color); }
.sm-next--warn .sm-next-val { color: #b45309; }
.sm-rows { display: flex; flex-direction: column; gap: 5px; }
.sm-row { display: flex; justify-content: space-between; font-size: 12px;
	color: var(--text-muted); }
.sm-row span:last-child { font-weight: 500; color: var(--text-color); }

/* Inactive */
.sm-irow { display: flex; gap: 12px; align-items: center; padding: 8px 12px;
	border-radius: 8px; cursor: pointer; background: var(--fg-color);
	border: 1px solid var(--border-color); opacity: .6; margin-bottom: 4px; }
.sm-irow:hover { opacity: 1; }
.sm-iname { font-size: 13px; font-weight: 500; flex: 1; }
.sm-icls  { font-size: 12px; color: var(--text-muted); }
.sm-imode { font-size: 11px; color: var(--text-muted); }

/* Timeline */
.sm-tl-row { display: flex; gap: 16px; align-items: flex-start;
	padding: 10px 0; border-bottom: 1px solid var(--border-color); }
.sm-tl-row:last-child { border-bottom: none; }
.sm-tl-date { font-size: 13px; font-weight: 700; min-width: 110px; flex-shrink: 0; }
.sm-tl-chips { display: flex; flex-wrap: wrap; gap: 6px; }
.sm-tl-chip { font-size: 12px; background: var(--subtle-fg); border: 1px solid var(--border-color);
	padding: 3px 10px; border-radius: 12px; }
.sm-loading, .sm-empty { color: var(--text-muted); font-size: 13px; padding: 20px 0; }
	`;
	document.head.appendChild(s);
}
