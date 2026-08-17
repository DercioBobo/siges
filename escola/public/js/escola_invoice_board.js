window.escola = window.escola || {};
escola.utils = escola.utils || {};

// ---------------------------------------------------------------------------
// Shared filter bar + summary cards + table used by both "Monitor de
// Facturas" (invoice_monitor) and "Central de Pagamentos" (payment_desk).
// Auto-loads on build, re-searches on every filter change (debounced for
// free text) — no "Pesquisar" button. Estado is multi-select via toggle
// pills. Pages differ only in query_module and row_action_html/on_row_action_click.
// ---------------------------------------------------------------------------

escola.utils.InvoiceBoard = class InvoiceBoard {
	constructor(page, opts) {
		this.page = page;
		this.$body = $(page.body);
		this.opts = opts;
		this.query_module = opts.query_module;
		this._turmas = [];
		this._rows = [];
		this._statuses = new Set(opts.default_statuses || []);
		this._build();
	}

	_build() {
		_ibd_styles();

		const STATUS_OPTIONS = [
			{ value: "Em Aberto", cls: "ibd-pill--gray" },
			{ value: "Em Dívida", cls: "ibd-pill--orange" },
			{ value: "Vencida",   cls: "ibd-pill--red" },
			{ value: "Paga",      cls: "ibd-pill--green" },
		];
		const pills = STATUS_OPTIONS.map(o => `
			<button type="button" class="ibd-pill ${o.cls} ${this._statuses.has(o.value) ? "ibd-pill--active" : ""}" data-status="${o.value}">
				${__(o.value)}
			</button>`).join("");

		this.$body.html(`
		<div class="ibd-wrap">
			<div class="ibd-filters">
				<div class="ibd-row">
					<div class="ibd-fg">
						<label>${__("Classe")}</label>
						<select id="ibd-cls"><option value="">${__("Todas")}</option></select>
					</div>
					<div class="ibd-fg">
						<label>${__("Turma")}</label>
						<select id="ibd-turma"><option value="">${__("Todas")}</option></select>
					</div>
					<div class="ibd-fg ibd-fg--grow">
						<label>${__("Aluno")}</label>
						<input id="ibd-student" type="text" placeholder="${__("Nome ou código…")}">
					</div>
					<div class="ibd-fg">
						<label>${__("De")}</label>
						<input id="ibd-from" type="date">
					</div>
					<div class="ibd-fg">
						<label>${__("Até")}</label>
						<input id="ibd-to" type="date">
					</div>
				</div>
				<div class="ibd-row">
					<div class="ibd-fg ibd-fg--grow">
						<label>${__("Estado")}</label>
						<div class="ibd-pills" id="ibd-status">${pills}</div>
					</div>
				</div>
			</div>

			<div class="ibd-summary" id="ibd-summary" style="display:none">
				<div class="ibd-card ibd-card--blue">
					<div class="ibd-card-lbl">${__("Total Facturado")}</div>
					<div class="ibd-card-val" id="ibd-s-total">—</div>
					<div class="ibd-card-sub" id="ibd-s-count"></div>
				</div>
				<div class="ibd-card ibd-card--green">
					<div class="ibd-card-lbl">${__("Total Pago")}</div>
					<div class="ibd-card-val" id="ibd-s-paid">—</div>
				</div>
				<div class="ibd-card ibd-card--orange">
					<div class="ibd-card-lbl">${__("Em Dívida")}</div>
					<div class="ibd-card-val" id="ibd-s-outstanding">—</div>
				</div>
				<div class="ibd-card ibd-card--red">
					<div class="ibd-card-lbl">${__("Vencido")}</div>
					<div class="ibd-card-val" id="ibd-s-overdue">—</div>
				</div>
			</div>

			<div class="ibd-tbl-wrap" id="ibd-tbl-wrap" style="display:none">
				<table class="ibd-tbl">
					<thead><tr>
						<th>${__("Aluno")}</th>
						<th>${__("Classe")}</th>
						<th>${__("Turma")}</th>
						<th>${__("Emissão")}</th>
						<th>${__("Vencimento")}</th>
						<th class="ibd-r">${__("Total")}</th>
						<th class="ibd-r">${__("Pago")}</th>
						<th class="ibd-r">${__("Em Dívida")}</th>
						<th>${__("Estado")}</th>
						<th></th>
					</tr></thead>
					<tbody id="ibd-tbody"></tbody>
				</table>
			</div>

			<div class="ibd-empty" id="ibd-empty" style="display:none">
				${__("Nenhuma factura encontrada.")}
			</div>
		</div>`);

		this._load_options();
		this._bind();
		this.search();
	}

	_bind() {
		this.$body.find("#ibd-cls").on("change", () => { this._filter_turmas(); this.search(); });
		this.$body.find("#ibd-turma").on("change", () => this.search());
		this.$body.find("#ibd-from, #ibd-to").on("change", () => this.search());
		this.$body.find("#ibd-student").on("input", escola.utils.debounce(() => this.search(), 350));

		this.$body.find("#ibd-status").on("click", ".ibd-pill", (e) => {
			const $btn = $(e.currentTarget);
			const status = $btn.data("status");
			if (this._statuses.has(status)) {
				this._statuses.delete(status);
				$btn.removeClass("ibd-pill--active");
			} else {
				this._statuses.add(status);
				$btn.addClass("ibd-pill--active");
			}
			this.search();
		});

		if (this.opts.on_row_action_click) {
			this.$body.find("#ibd-tbody").on("click", (e) => {
				const name = $(e.target).closest("tr").data("name");
				const row = this._rows.find(r => r.invoice === name);
				if (row) this.opts.on_row_action_click($(e.target), row);
			});
		}
	}

	async _load_options() {
		const r = await frappe.call({ method: `${this.query_module}.get_filter_options` });
		if (!r.message) return;
		const { classes, turmas } = r.message;
		this._turmas = turmas || [];

		const $c = this.$body.find("#ibd-cls");
		(classes || []).forEach(c =>
			$c.append(`<option value="${c.name}">${frappe.utils.escape_html(c.class_name || c.name)}</option>`)
		);
		this._populate_turmas("");
	}

	_filter_turmas() {
		this._populate_turmas(this.$body.find("#ibd-cls").val());
	}

	_populate_turmas(cls) {
		const $t = this.$body.find("#ibd-turma").empty()
			.append(`<option value="">${__("Todas")}</option>`);
		const list = cls ? this._turmas.filter(t => t.school_class === cls) : this._turmas;
		list.forEach(t =>
			$t.append(`<option value="${t.name}">${frappe.utils.escape_html(t.group_name || t.name)}</option>`)
		);
	}

	async search() {
		const r = await frappe.call({
			method: `${this.query_module}.get_invoices`,
			args: {
				from_date:    this.$body.find("#ibd-from").val()    || null,
				to_date:      this.$body.find("#ibd-to").val()      || null,
				school_class: this.$body.find("#ibd-cls").val()     || null,
				class_group:  this.$body.find("#ibd-turma").val()   || null,
				student:      this.$body.find("#ibd-student").val() || null,
				status:       Array.from(this._statuses),
			},
		});
		if (r && r.exc) {
			this._rows = [];
			this.$body.find("#ibd-tbl-wrap, #ibd-summary").hide();
			this.$body.find("#ibd-empty")
				.css("color", "var(--red-500)")
				.text(__("Erro ao carregar dados. Verifique o registo de erros do servidor."))
				.show();
			return;
		}
		if (r && r.message) this._render(r.message);
	}

	_render({ rows, summary }) {
		this._rows = rows || [];

		const $sum = this.$body.find("#ibd-summary").show();
		$sum.find("#ibd-s-total").text(format_currency(summary.total_invoiced));
		$sum.find("#ibd-s-count").text(__("{0} factura(s)", [summary.count]));
		$sum.find("#ibd-s-paid").text(format_currency(summary.total_paid));
		$sum.find("#ibd-s-outstanding").text(format_currency(summary.total_outstanding));
		$sum.find("#ibd-s-overdue").text(format_currency(summary.total_overdue));

		const BADGE = {
			"Em Aberto": "ibd-b--gray",
			"Paga":      "ibd-b--green",
			"Em Dívida": "ibd-b--orange",
			"Vencida":   "ibd-b--red",
		};

		this.$body.find("#ibd-empty").css("color", "").text(__("Nenhuma factura encontrada."));

		if (!this._rows.length) {
			this.$body.find("#ibd-tbl-wrap").hide();
			this.$body.find("#ibd-empty").show();
			return;
		}
		this.$body.find("#ibd-empty").hide();
		this.$body.find("#ibd-tbl-wrap").show();

		const html = this._rows.map(r => `
		<tr data-name="${frappe.utils.escape_html(r.invoice)}">
			<td>
				<div class="ibd-sname">${frappe.utils.escape_html(r.student_name || r.student)}</div>
				<div class="ibd-sid">${frappe.utils.escape_html(r.student)}</div>
			</td>
			<td>${frappe.utils.escape_html(r.school_class || "—")}</td>
			<td>${frappe.utils.escape_html(r.turma_name  || "—")}</td>
			<td>${frappe.datetime.str_to_user(r.posting_date)}</td>
			<td>${frappe.datetime.str_to_user(r.due_date)}</td>
			<td class="ibd-r">${format_currency(r.grand_total)}</td>
			<td class="ibd-r">${format_currency(r.paid)}</td>
			<td class="ibd-r">${format_currency(r.outstanding_amount)}</td>
			<td><span class="ibd-b ${BADGE[r.display_status] || ""}">${r.display_status}</span></td>
			<td>${this.opts.row_action_html ? this.opts.row_action_html(r) : ""}</td>
		</tr>`).join("");

		this.$body.find("#ibd-tbody").html(html);
	}
};

function _ibd_styles() {
	if (document.getElementById("ibd-css")) return;
	const s = document.createElement("style");
	s.id = "ibd-css";
	s.textContent = `
.ibd-wrap { padding: 16px 20px; }

/* ── Filters ─── */
.ibd-filters { background: var(--fg-color); border: 1px solid var(--border-color);
	border-radius: 10px; padding: 14px 16px; margin-bottom: 16px; display: flex; flex-direction: column; gap: 10px; }
.ibd-row { display: flex; flex-wrap: wrap; gap: 10px; align-items: flex-end; }
.ibd-fg { display: flex; flex-direction: column; gap: 4px; min-width: 110px; }
.ibd-fg--grow { flex: 1; min-width: 160px; }
.ibd-fg label { font-size: 11px; font-weight: 600; color: var(--text-muted);
	text-transform: uppercase; letter-spacing: .5px; }
.ibd-fg select, .ibd-fg input[type=text], .ibd-fg input[type=date] {
	height: 32px; padding: 0 9px; border: 1.5px solid var(--border-color);
	border-radius: 6px; font-size: 13px; background: var(--fg-color);
	color: var(--text-color); outline: none; transition: border-color .15s; }
.ibd-fg select:focus, .ibd-fg input:focus { border-color: var(--primary); }

/* ── Estado pills ─── */
.ibd-pills { display: flex; flex-wrap: wrap; gap: 8px; }
.ibd-pill { font-size: 12px; font-weight: 600; padding: 6px 14px; border-radius: 16px;
	border: 1.5px solid var(--border-color); background: var(--fg-color); color: var(--text-muted);
	cursor: pointer; transition: all .12s; }
.ibd-pill:hover { border-color: var(--primary); }
.ibd-pill--active.ibd-pill--gray   { background: #e5e7eb; color: #374151; border-color: #9ca3af; }
.ibd-pill--active.ibd-pill--green  { background: #dcfce7; color: #166534; border-color: #10b981; }
.ibd-pill--active.ibd-pill--orange { background: #fef3c7; color: #92400e; border-color: #f59e0b; }
.ibd-pill--active.ibd-pill--red    { background: #fee2e2; color: #991b1b; border-color: #ef4444; }

/* ── Summary cards ─── */
.ibd-summary { display: flex; gap: 12px; margin-bottom: 16px; flex-wrap: wrap; }
.ibd-card { flex: 1; min-width: 140px; padding: 14px 16px; border-radius: 10px;
	background: var(--fg-color); border: 1px solid var(--border-color);
	border-left: 4px solid transparent; }
.ibd-card--blue   { border-left-color: #3b82f6; }
.ibd-card--green  { border-left-color: #10b981; }
.ibd-card--orange { border-left-color: #f59e0b; }
.ibd-card--red    { border-left-color: #ef4444; }
.ibd-card-lbl { font-size: 11px; font-weight: 600; color: var(--text-muted);
	text-transform: uppercase; letter-spacing: .5px; margin-bottom: 5px; }
.ibd-card-val { font-size: 20px; font-weight: 700; color: var(--text-color); }
.ibd-card-sub { font-size: 12px; color: var(--text-muted); margin-top: 2px; }

/* ── Table ─── */
.ibd-tbl-wrap { border: 1px solid var(--border-color); border-radius: 10px; overflow: hidden; }
.ibd-tbl { width: 100%; border-collapse: collapse; font-size: 13px; }
.ibd-tbl thead tr { background: var(--subtle-fg); }
.ibd-tbl th { padding: 9px 12px; text-align: left; font-size: 11px; font-weight: 700;
	color: var(--text-muted); text-transform: uppercase; letter-spacing: .5px;
	border-bottom: 1px solid var(--border-color); white-space: nowrap; }
.ibd-tbl td { padding: 9px 12px; border-bottom: 1px solid var(--border-color); vertical-align: middle; }
.ibd-tbl tbody tr:last-child td { border-bottom: none; }
.ibd-tbl tbody tr:hover { background: var(--subtle-fg); }
.ibd-r { text-align: right; font-variant-numeric: tabular-nums; }
.ibd-sname { font-weight: 500; }
.ibd-sid   { font-size: 11px; color: var(--text-muted); }
.ibd-b { font-size: 11px; font-weight: 600; padding: 3px 9px; border-radius: 12px; white-space: nowrap; }
.ibd-b--gray   { background: #e5e7eb; color: #374151; }
.ibd-b--green  { background: #dcfce7; color: #166534; }
.ibd-b--orange { background: #fef3c7; color: #92400e; }
.ibd-b--red    { background: #fee2e2; color: #991b1b; }
.ibd-link { font-size: 15px; color: var(--text-muted); text-decoration: none; }
.ibd-link:hover { color: var(--primary); }
.ibd-muted { color: var(--text-muted); }
.ibd-empty { text-align: center; padding: 48px 20px; color: var(--text-muted); font-size: 14px; }
	`;
	document.head.appendChild(s);
}
