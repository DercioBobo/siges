window.escola = window.escola || {};
escola.utils = escola.utils || {};

// ---------------------------------------------------------------------------
// Shared filter bar + summary cards + table used by both "Monitor de
// Facturas" (invoice_monitor) and "Central de Pagamentos" (payment_desk).
// Auto-loads on build, re-searches on every filter change (debounced for
// free text) — no "Pesquisar" button. Estado is multi-select via toggle
// pills. Pages differ only in query_module and row_action_html/on_row_action_click.
// ---------------------------------------------------------------------------

const IBD_MONTHS = [
	"Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
	"Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
];

escola.utils.InvoiceBoard = class InvoiceBoard {
	constructor(page, opts) {
		this.page = page;
		this.$body = $(page.body);
		this.opts = opts;
		this.query_module = opts.query_module;
		this._turmas = [];
		this._rows = [];
		this._statuses = new Set(opts.default_statuses || []);
		this._with_penalty = false;
		this._build();
	}

	_build() {
		_ibd_styles();

		const STATUS_OPTIONS = [
			{ value: "Em Aberto", cls: "ibd-pill--gray" },
			{ value: "Em Dívida", cls: "ibd-pill--orange" },
			{ value: "Vencida",   cls: "ibd-pill--red" },
			{ value: "Parcialmente Paga", cls: "ibd-pill--blue" },
			{ value: "Paga",      cls: "ibd-pill--green" },
		];
		const pills = `
			<button type="button" class="ibd-pill ibd-pill--all" data-status="">${__("Todos")}</button>`
			+ STATUS_OPTIONS.map(o => `
			<button type="button" class="ibd-pill ${o.cls}" data-status="${o.value}">
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
						<label>${__("Mês")}</label>
						<select id="ibd-month">
							<option value="">${__("Todos")}</option>
							${IBD_MONTHS.map((m, i) => `<option value="${i + 1}">${__(m)}</option>`).join("")}
						</select>
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
						<div class="ibd-pills">
							<span id="ibd-status" class="ibd-pills">${pills}</span>
							<span class="ibd-pill-sep"></span>
							<button type="button" class="ibd-pill ibd-pill--purple" id="ibd-penalty"
								title="${__("Mostra apenas facturas com multa (combina com o Estado)")}">
								${__("Com Multa")}
							</button>
						</div>
						<div class="ibd-hint">${__("Clique para filtrar por um estado · Ctrl+clique para seleccionar vários")}</div>
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
						<th>${__("Factura")}</th>
						<th>${__("Aluno")}</th>
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

		this._sync_pills();
		this._load_options();
		this._bind();
		this.search();
	}

	_bind() {
		this.$body.find("#ibd-cls").on("change", () => { this._filter_turmas(); this.search(); });
		this.$body.find("#ibd-turma").on("change", () => this.search());
		// Picking a month fills De/Até with that month of the current year;
		// editing De/Até by hand clears the month so they never disagree.
		this.$body.find("#ibd-month").on("change", (e) => {
			const month = parseInt($(e.currentTarget).val(), 10);
			if (month) {
				const year = new Date().getFullYear();
				const last = new Date(year, month, 0).getDate();
				const mm = String(month).padStart(2, "0");
				this.$body.find("#ibd-from").val(`${year}-${mm}-01`);
				this.$body.find("#ibd-to").val(`${year}-${mm}-${last}`);
			} else {
				this.$body.find("#ibd-from, #ibd-to").val("");
			}
			this.search();
		});
		this.$body.find("#ibd-from, #ibd-to").on("change", () => {
			this.$body.find("#ibd-month").val("");
			this.search();
		});
		this.$body.find("#ibd-student").on("input", _ibd_debounce(() => this.search(), 350));

		// Click = only this state (click it again → Todos).
		// Ctrl/Cmd/Shift+click = add/remove it from the current selection.
		this.$body.find("#ibd-status").on("click", ".ibd-pill", (e) => {
			const status = $(e.currentTarget).attr("data-status");
			const multi = e.ctrlKey || e.metaKey || e.shiftKey;
			if (!status) {
				this._statuses.clear();
			} else if (multi) {
				if (this._statuses.has(status)) this._statuses.delete(status);
				else this._statuses.add(status);
			} else if (this._statuses.size === 1 && this._statuses.has(status)) {
				this._statuses.clear();
			} else {
				this._statuses = new Set([status]);
			}
			this._sync_pills();
			this.search();
		});

		this.$body.find("#ibd-penalty").on("click", (e) => {
			this._with_penalty = !this._with_penalty;
			$(e.currentTarget).toggleClass("ibd-pill--active", this._with_penalty);
			this.search();
		});

		this.$body.find("#ibd-tbody").on("click", ".ibd-student-link", (e) => {
			e.preventDefault();
			e.stopPropagation();
			escola.utils.open_student_statement($(e.currentTarget).attr("data-student"), {
				query_module: this.query_module,
			});
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

	_sync_pills() {
		this.$body.find("#ibd-status .ibd-pill").each((_i, el) => {
			const status = el.getAttribute("data-status");
			const active = status ? this._statuses.has(status) : this._statuses.size === 0;
			el.classList.toggle("ibd-pill--active", active);
		});
	}

	_penalty_tag(r) {
		const line = flt(r.penalty_amount);
		const amount = line || flt(r.dynamic_penalty);
		if (!amount) return "";
		const title = line ? __("Multa na factura") : __("Multa calculada (modo Dinâmico)");
		return `<span class="ibd-b ibd-b--purple" title="${title}">${__("Multa")} ${_ibd_amount(amount)}</span>`;
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
		// Responses can arrive out of order (a big "Paga" query finishing after
		// a quick "Vencida" one) — only the latest request may render.
		const seq = this._search_seq = (this._search_seq || 0) + 1;
		this.$body.find(".ibd-wrap").addClass("ibd-loading");
		const r = await frappe.call({
			method: `${this.query_module}.get_invoices`,
			args: {
				from_date:    this.$body.find("#ibd-from").val()    || null,
				to_date:      this.$body.find("#ibd-to").val()      || null,
				school_class: this.$body.find("#ibd-cls").val()     || null,
				class_group:  this.$body.find("#ibd-turma").val()   || null,
				student:      this.$body.find("#ibd-student").val() || null,
				status:       Array.from(this._statuses),
				with_penalty: this._with_penalty ? 1 : 0,
			},
		}).catch(() => null);
		if (seq !== this._search_seq) return;
		this.$body.find(".ibd-wrap").removeClass("ibd-loading");
		if (!r || r.exc) {
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
			"Parcialmente Paga": "ibd-b--blue",
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
			<td><a href="/app/sales-invoice/${encodeURIComponent(r.invoice)}" target="_blank"
				class="ibd-inv-link">${frappe.utils.escape_html(r.invoice)}</a></td>
			<td>
				<a class="ibd-sname ibd-student-link" data-student="${frappe.utils.escape_html(r.student)}"
					title="${__("Ver extrato do aluno")}">${frappe.utils.escape_html(r.student_name || r.student)}</a>
				<div class="ibd-sid">${frappe.utils.escape_html(r.student)}</div>
			</td>
			<td class="ibd-nw">${frappe.utils.escape_html(r.turma_name  || "—")}</td>
			<td class="ibd-nw">${frappe.datetime.str_to_user(r.posting_date)}</td>
			<td class="ibd-nw">${frappe.datetime.str_to_user(r.due_date)}</td>
			<td class="ibd-r ibd-nw">${_ibd_amount(r.grand_total)}</td>
			<td class="ibd-r ibd-nw">${_ibd_amount(r.paid)}</td>
			<td class="ibd-r ibd-nw">${_ibd_amount(r.outstanding_amount)}</td>
			<td>
				<span class="ibd-b ${BADGE[r.display_status] || ""}">${__(r.display_status)}</span>
				${this._penalty_tag(r)}
			</td>
			<td>${this.opts.row_action_html ? this.opts.row_action_html(r) : ""}</td>
		</tr>`).join("");

		this.$body.find("#ibd-tbody").html(html);
	}
};

// ---------------------------------------------------------------------------
// Mini extrato do aluno — opened from the Aluno name on either board.
// ---------------------------------------------------------------------------

const IBD_STMT_STATUS = {
	// get_student_invoices vocabulary → the boards' Estado vocabulary
	"Rascunho":  { label: "Em Aberto", cls: "ibd-b--gray" },
	"Paga":      { label: "Paga",      cls: "ibd-b--green" },
	"Em Atraso": { label: "Vencida",   cls: "ibd-b--red" },
	"Emitida":   { label: "Em Dívida", cls: "ibd-b--orange" },
};

escola.utils.open_student_statement = async function (student, { query_module } = {}) {
	_ibd_styles();
	const d = new frappe.ui.Dialog({ title: __("Extrato do Aluno"), size: "extra-large" });
	d.$body.html(`<div class="ibd-stmt-loading">${__("A carregar…")}</div>`);
	d.show();

	const r = await frappe.call({
		method: `${query_module || "escola.escola.invoice_query"}.get_student_statement`,
		args: { student },
	}).catch(() => null);
	if (!r || !r.message) {
		d.$body.html(`<div class="ibd-stmt-loading">${__("Não foi possível carregar o extrato.")}</div>`);
		return;
	}

	const { student: st, invoices, payments, summary } = r.message;
	const esc = (v) => frappe.utils.escape_html(v == null ? "" : String(v));
	d.set_title(__("Extrato — {0}", [st.full_name]));

	const contact = [st.phone, st.primary_guardian && `${st.primary_guardian}${st.guardian_phone ? " · " + st.guardian_phone : ""}`]
		.filter(Boolean).map(esc).join(" &nbsp;|&nbsp; ");

	const inv_rows = invoices.map((i) => {
		let s = IBD_STMT_STATUS[i.status] || { label: i.status, cls: "" };
		if (i.status !== "Paga" && i.status !== "Rascunho" && i.paid > 0) {
			s = { label: "Parcialmente Paga", cls: "ibd-b--blue" };
		}
		return `
		<tr>
			<td><a href="/app/sales-invoice/${encodeURIComponent(i.name)}" target="_blank" class="ibd-inv-link">${esc(i.name)}</a></td>
			<td class="ibd-nw">${esc(i.mes_referencia !== "—" ? i.mes_referencia : i.posting_date)}</td>
			<td class="ibd-nw">${esc(i.due_date)}</td>
			<td class="ibd-r ibd-nw">${_ibd_amount(i.grand_total)}</td>
			<td class="ibd-r ibd-nw">${i.multa ? _ibd_amount(i.multa) : "—"}</td>
			<td class="ibd-r ibd-nw">${_ibd_amount(i.paid)}</td>
			<td class="ibd-r ibd-nw ${i.owed > 0 ? "ibd-stmt-owed" : ""}">${_ibd_amount(i.owed)}</td>
			<td><span class="ibd-b ${s.cls}">${__(s.label)}</span></td>
		</tr>`;
	}).join("");

	const pay_rows = payments.map((p) => `
		<tr>
			<td class="ibd-nw">${frappe.datetime.str_to_user(p.posting_date)}</td>
			<td><a href="/app/payment-entry/${encodeURIComponent(p.name)}" target="_blank" class="ibd-inv-link">${esc(p.name)}</a></td>
			<td>${esc(p.mode_of_payment || "—")}</td>
			<td>${esc(p.invoice)}</td>
			<td class="ibd-r ibd-nw">${_ibd_amount(p.amount)}</td>
		</tr>`).join("");

	const last = summary.last_payment;
	d.$body.html(`
	<div class="ibd-stmt">
		<div class="ibd-stmt-head">
			<div>
				<div class="ibd-stmt-name">${esc(st.full_name)}
					<span class="ibd-sid">${esc(st.student_code || st.name)}</span></div>
				<div class="ibd-stmt-meta">
					${esc(st.turma_name || st.current_school_class || "—")}
					&nbsp;·&nbsp; ${esc(st.current_status || "—")}
					&nbsp;·&nbsp; ${__("Situação financeira")}: <b>${esc(st.financial_status || "—")}</b>
				</div>
				${contact ? `<div class="ibd-stmt-meta">${contact}</div>` : ""}
			</div>
			<a class="btn btn-xs btn-default" href="/app/student/${encodeURIComponent(st.name)}" target="_blank">${__("Abrir ficha")}</a>
		</div>

		<div class="ibd-summary ibd-stmt-cards">
			<div class="ibd-card ibd-card--blue">
				<div class="ibd-card-lbl">${__("Facturado")}</div>
				<div class="ibd-card-val">${format_currency(summary.total_invoiced)}</div>
				<div class="ibd-card-sub">${__("{0} factura(s)", [summary.count])}</div>
			</div>
			<div class="ibd-card ibd-card--green">
				<div class="ibd-card-lbl">${__("Pago")}</div>
				<div class="ibd-card-val">${format_currency(summary.total_paid)}</div>
				<div class="ibd-card-sub">${last
					? __("Último: {0} em {1}", [_ibd_amount(last.amount), frappe.datetime.str_to_user(last.posting_date)])
					: __("Sem pagamentos")}</div>
			</div>
			<div class="ibd-card ibd-card--orange">
				<div class="ibd-card-lbl">${__("Em Dívida")}</div>
				<div class="ibd-card-val">${format_currency(summary.total_owed)}</div>
			</div>
		</div>

		<div class="ibd-stmt-title">${__("Últimas facturas")}</div>
		<div class="ibd-tbl-wrap">
			<table class="ibd-tbl">
				<thead><tr>
					<th>${__("Factura")}</th><th>${__("Mês / Emissão")}</th><th>${__("Vencimento")}</th>
					<th class="ibd-r">${__("Total")}</th><th class="ibd-r">${__("Multa")}</th>
					<th class="ibd-r">${__("Pago")}</th><th class="ibd-r">${__("Em Dívida")}</th><th>${__("Estado")}</th>
				</tr></thead>
				<tbody>${inv_rows || `<tr><td colspan="8" class="ibd-stmt-empty">${__("Sem facturas.")}</td></tr>`}</tbody>
			</table>
		</div>

		<div class="ibd-stmt-title">${__("Últimos pagamentos")}</div>
		<div class="ibd-tbl-wrap">
			<table class="ibd-tbl">
				<thead><tr>
					<th>${__("Data")}</th><th>${__("Pagamento")}</th><th>${__("Modo")}</th>
					<th>${__("Factura")}</th><th class="ibd-r">${__("Valor")}</th>
				</tr></thead>
				<tbody>${pay_rows || `<tr><td colspan="5" class="ibd-stmt-empty">${__("Sem pagamentos registados.")}</td></tr>`}</tbody>
			</table>
		</div>
	</div>`);
};

// Table cells show plain numbers — the currency symbol on every cell made
// the amounts wrap onto two lines. Summary cards keep format_currency.
function _ibd_amount(value) {
	return format_number(flt(value), null, 2);
}

function _ibd_debounce(fn, wait) {
	let t;
	return function (...args) {
		clearTimeout(t);
		t = setTimeout(() => fn.apply(this, args), wait);
	};
}

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
.ibd-pill--active.ibd-pill--blue   { background: #dbeafe; color: #1e40af; border-color: #3b82f6; }
.ibd-pill--active.ibd-pill--purple { background: #ede9fe; color: #5b21b6; border-color: #8b5cf6; }
.ibd-pill--active.ibd-pill--all    { background: var(--primary); color: #fff; border-color: var(--primary); }
.ibd-hint { font-size: 11px; color: var(--text-muted); margin-top: 2px; }
.ibd-loading .ibd-tbl-wrap, .ibd-loading .ibd-summary { opacity: .45; pointer-events: none; transition: opacity .15s; }
.ibd-student-link { cursor: pointer; color: var(--text-color); display: block; }
.ibd-student-link:hover { color: var(--primary); text-decoration: underline; }
.ibd-stmt-loading { padding: 30px; text-align: center; color: var(--text-muted); }
.ibd-stmt-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; margin-bottom: 14px; }
.ibd-stmt-name { font-size: 16px; font-weight: 600; }
.ibd-stmt-name .ibd-sid { margin-left: 6px; }
.ibd-stmt-meta { font-size: 12px; color: var(--text-muted); margin-top: 3px; }
.ibd-stmt-cards { margin-bottom: 12px; }
.ibd-stmt-title { font-size: 11px; font-weight: 700; color: var(--text-muted); text-transform: uppercase;
	letter-spacing: .5px; margin: 14px 0 6px; }
.ibd-stmt-owed { font-weight: 600; color: #b45309; }
.ibd-stmt-empty { text-align: center; color: var(--text-muted); }
.ibd-pill-sep { width: 1px; align-self: stretch; background: var(--border-color); margin: 0 4px; }
.ibd-inv-link { font-weight: 600; white-space: nowrap; }

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
.ibd-tbl-wrap { border: 1px solid var(--border-color); border-radius: 10px; overflow-x: auto; }
.ibd-tbl { width: 100%; border-collapse: collapse; font-size: 13px; }
.ibd-tbl thead tr { background: var(--subtle-fg); }
.ibd-tbl th { padding: 9px 12px; text-align: left; font-size: 11px; font-weight: 700;
	color: var(--text-muted); text-transform: uppercase; letter-spacing: .5px;
	border-bottom: 1px solid var(--border-color); white-space: nowrap; }
.ibd-tbl td { padding: 9px 12px; border-bottom: 1px solid var(--border-color); vertical-align: middle; }
.ibd-tbl tbody tr:last-child td { border-bottom: none; }
.ibd-tbl tbody tr:hover { background: var(--subtle-fg); }
.ibd-r { text-align: right; font-variant-numeric: tabular-nums; }
.ibd-nw { white-space: nowrap; }
.ibd-tbl th.ibd-r { text-align: right; }
.ibd-b--purple { white-space: nowrap; }
.ibd-sname { font-weight: 500; }
.ibd-sid   { font-size: 11px; color: var(--text-muted); }
.ibd-b { font-size: 11px; font-weight: 600; padding: 3px 9px; border-radius: 12px; white-space: nowrap; }
.ibd-b--gray   { background: #e5e7eb; color: #374151; }
.ibd-b--green  { background: #dcfce7; color: #166534; }
.ibd-b--orange { background: #fef3c7; color: #92400e; }
.ibd-b--red    { background: #fee2e2; color: #991b1b; }
.ibd-b--blue   { background: #dbeafe; color: #1e40af; }
.ibd-b--purple { background: #ede9fe; color: #5b21b6; margin-left: 4px; }
.ibd-link { font-size: 15px; color: var(--text-muted); text-decoration: none; }
.ibd-link:hover { color: var(--primary); }
.ibd-muted { color: var(--text-muted); }
.ibd-empty { text-align: center; padding: 48px 20px; color: var(--text-muted); font-size: 14px; }
	`;
	document.head.appendChild(s);
}
