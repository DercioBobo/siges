frappe.pages["invoice-monitor"] = {};

frappe.pages["invoice-monitor"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Monitor de Facturas"),
		single_column: true,
	});
	new InvoiceMonitor(page);
};

class InvoiceMonitor {
	constructor(page) {
		this.page      = page;
		this.$body     = $(page.body);
		this._turmas   = [];
		this._build();
	}

	_build() {
		_im_styles();
		this.$body.html(`
		<div class="im-wrap">
			<div class="im-filters">
				<div class="im-row">
					<div class="im-fg">
						<label>${__("Classe")}</label>
						<select id="im-cls"><option value="">${__("Todas")}</option></select>
					</div>
					<div class="im-fg">
						<label>${__("Turma")}</label>
						<select id="im-turma"><option value="">${__("Todas")}</option></select>
					</div>
					<div class="im-fg im-fg--grow">
						<label>${__("Aluno")}</label>
						<input id="im-student" type="text" placeholder="${__("Nome ou código…")}">
					</div>
					<div class="im-fg">
						<label>${__("De")}</label>
						<input id="im-from" type="date">
					</div>
					<div class="im-fg">
						<label>${__("Até")}</label>
						<input id="im-to" type="date">
					</div>
					<div class="im-fg">
						<label>${__("Estado")}</label>
						<select id="im-status">
							<option value="">${__("Todos")}</option>
							<option value="Paga">${__("Paga")}</option>
							<option value="Em Dívida">${__("Em Dívida")}</option>
							<option value="Vencida">${__("Vencida")}</option>
						</select>
					</div>
					<div class="im-fg im-fg--btns">
						<button class="btn btn-primary btn-sm" id="im-search">${__("Pesquisar")}</button>
						<button class="btn btn-default btn-sm"  id="im-clear">${__("Limpar")}</button>
					</div>
				</div>
			</div>

			<div class="im-summary" id="im-summary" style="display:none">
				<div class="im-card im-card--blue">
					<div class="im-card-lbl">${__("Total Facturado")}</div>
					<div class="im-card-val" id="im-s-total">—</div>
					<div class="im-card-sub" id="im-s-count"></div>
				</div>
				<div class="im-card im-card--green">
					<div class="im-card-lbl">${__("Total Pago")}</div>
					<div class="im-card-val" id="im-s-paid">—</div>
				</div>
				<div class="im-card im-card--orange">
					<div class="im-card-lbl">${__("Em Dívida")}</div>
					<div class="im-card-val" id="im-s-outstanding">—</div>
				</div>
				<div class="im-card im-card--red">
					<div class="im-card-lbl">${__("Vencido")}</div>
					<div class="im-card-val" id="im-s-overdue">—</div>
				</div>
			</div>

			<div class="im-tbl-wrap" id="im-tbl-wrap" style="display:none">
				<table class="im-tbl">
					<thead><tr>
						<th>${__("Aluno")}</th>
						<th>${__("Classe")}</th>
						<th>${__("Turma")}</th>
						<th>${__("Emissão")}</th>
						<th>${__("Vencimento")}</th>
						<th class="im-r">${__("Total")}</th>
						<th class="im-r">${__("Pago")}</th>
						<th class="im-r">${__("Em Dívida")}</th>
						<th>${__("Estado")}</th>
						<th></th>
					</tr></thead>
					<tbody id="im-tbody"></tbody>
				</table>
			</div>

			<div class="im-empty" id="im-empty" style="display:none">
				${__("Nenhuma factura encontrada.")}
			</div>
		</div>`);

		this._load_options();
		this._bind();
	}

	_bind() {
		this.$body.find("#im-cls").on("change",    ()  => this._filter_turmas());
		this.$body.find("#im-search").on("click",  ()  => this.search());
		this.$body.find("#im-clear").on("click",   ()  => this._clear());
		this.$body.find("#im-student").on("keydown", e => { if (e.key === "Enter") this.search(); });
	}

	async _load_options() {
		const r = await frappe.call({
			method: "escola.escola.page.invoice_monitor.invoice_monitor.get_filter_options",
		});
		if (!r.message) return;
		const { classes, turmas } = r.message;
		this._turmas = turmas || [];

		const $c = this.$body.find("#im-cls");
		(classes || []).forEach(c =>
			$c.append(`<option value="${c.name}">${frappe.utils.escape_html(c.class_name || c.name)}</option>`)
		);
		this._populate_turmas("");
	}

	_filter_turmas() {
		this._populate_turmas(this.$body.find("#im-cls").val());
	}

	_populate_turmas(cls) {
		const $t = this.$body.find("#im-turma").empty()
			.append(`<option value="">${__("Todas")}</option>`);
		const list = cls ? this._turmas.filter(t => t.school_class === cls) : this._turmas;
		list.forEach(t =>
			$t.append(`<option value="${t.name}">${frappe.utils.escape_html(t.group_name || t.name)}</option>`)
		);
	}

	async search() {
		const $btn = this.$body.find("#im-search").prop("disabled", true).text(__("A pesquisar…"));
		try {
			const r = await frappe.call({
				method: "escola.escola.page.invoice_monitor.invoice_monitor.get_invoices",
				args: {
					from_date:    this.$body.find("#im-from").val()    || null,
					to_date:      this.$body.find("#im-to").val()      || null,
					school_class: this.$body.find("#im-cls").val()     || null,
					class_group:  this.$body.find("#im-turma").val()   || null,
					student:      this.$body.find("#im-student").val() || null,
					status:       this.$body.find("#im-status").val()  || null,
				},
			});
			if (r.message) this._render(r.message);
		} finally {
			$btn.prop("disabled", false).text(__("Pesquisar"));
		}
	}

	_render({ rows, summary }) {
		const $sum = this.$body.find("#im-summary").show();
		$sum.find("#im-s-total").text(format_currency(summary.total_invoiced));
		$sum.find("#im-s-count").text(__("{0} factura(s)", [summary.count]));
		$sum.find("#im-s-paid").text(format_currency(summary.total_paid));
		$sum.find("#im-s-outstanding").text(format_currency(summary.total_outstanding));
		$sum.find("#im-s-overdue").text(format_currency(summary.total_overdue));

		const BADGE = {
			"Paga":      "im-b--green",
			"Em Dívida": "im-b--orange",
			"Vencida":   "im-b--red",
		};

		if (!rows.length) {
			this.$body.find("#im-tbl-wrap").hide();
			this.$body.find("#im-empty").show();
			return;
		}
		this.$body.find("#im-empty").hide();
		this.$body.find("#im-tbl-wrap").show();

		const html = rows.map(r => `
		<tr>
			<td>
				<div class="im-sname">${frappe.utils.escape_html(r.student_name || r.student)}</div>
				<div class="im-sid">${frappe.utils.escape_html(r.student)}</div>
			</td>
			<td>${frappe.utils.escape_html(r.school_class || "—")}</td>
			<td>${frappe.utils.escape_html(r.turma_name  || "—")}</td>
			<td>${frappe.datetime.str_to_user(r.posting_date)}</td>
			<td>${frappe.datetime.str_to_user(r.due_date)}</td>
			<td class="im-r">${format_currency(r.grand_total)}</td>
			<td class="im-r">${format_currency(r.paid)}</td>
			<td class="im-r">${format_currency(r.outstanding_amount)}</td>
			<td><span class="im-b ${BADGE[r.display_status] || ""}">${r.display_status}</span></td>
			<td><a href="/app/sales-invoice/${r.invoice}" target="_blank" class="im-link" title="${__("Abrir factura")}">↗</a></td>
		</tr>`).join("");

		this.$body.find("#im-tbody").html(html);
	}

	_clear() {
		this.$body.find("#im-cls, #im-turma, #im-status").val("");
		this.$body.find("#im-student, #im-from, #im-to").val("");
		this._populate_turmas("");
		this.$body.find("#im-summary, #im-tbl-wrap, #im-empty").hide();
	}
}

function _im_styles() {
	if (document.getElementById("im-css")) return;
	const s = document.createElement("style");
	s.id = "im-css";
	s.textContent = `
.im-wrap { padding: 16px 20px; }

/* ── Filters ─── */
.im-filters { background: var(--fg-color); border: 1px solid var(--border-color);
	border-radius: 10px; padding: 14px 16px; margin-bottom: 16px; }
.im-row { display: flex; flex-wrap: wrap; gap: 10px; align-items: flex-end; }
.im-fg { display: flex; flex-direction: column; gap: 4px; min-width: 110px; }
.im-fg--grow { flex: 1; min-width: 160px; }
.im-fg--btns { flex-direction: row; gap: 6px; align-items: flex-end; min-width: unset; }
.im-fg label { font-size: 11px; font-weight: 600; color: var(--text-muted);
	text-transform: uppercase; letter-spacing: .5px; }
.im-fg select, .im-fg input[type=text], .im-fg input[type=date] {
	height: 32px; padding: 0 9px; border: 1.5px solid var(--border-color);
	border-radius: 6px; font-size: 13px; background: var(--fg-color);
	color: var(--text-color); outline: none; transition: border-color .15s; }
.im-fg select:focus, .im-fg input:focus { border-color: var(--primary); }

/* ── Summary cards ─── */
.im-summary { display: flex; gap: 12px; margin-bottom: 16px; flex-wrap: wrap; }
.im-card { flex: 1; min-width: 140px; padding: 14px 16px; border-radius: 10px;
	background: var(--fg-color); border: 1px solid var(--border-color);
	border-left: 4px solid transparent; }
.im-card--blue   { border-left-color: #3b82f6; }
.im-card--green  { border-left-color: #10b981; }
.im-card--orange { border-left-color: #f59e0b; }
.im-card--red    { border-left-color: #ef4444; }
.im-card-lbl { font-size: 11px; font-weight: 600; color: var(--text-muted);
	text-transform: uppercase; letter-spacing: .5px; margin-bottom: 5px; }
.im-card-val { font-size: 20px; font-weight: 700; color: var(--text-color); }
.im-card-sub { font-size: 12px; color: var(--text-muted); margin-top: 2px; }

/* ── Table ─── */
.im-tbl-wrap { border: 1px solid var(--border-color); border-radius: 10px; overflow: hidden; }
.im-tbl { width: 100%; border-collapse: collapse; font-size: 13px; }
.im-tbl thead tr { background: var(--subtle-fg); }
.im-tbl th { padding: 9px 12px; text-align: left; font-size: 11px; font-weight: 700;
	color: var(--text-muted); text-transform: uppercase; letter-spacing: .5px;
	border-bottom: 1px solid var(--border-color); white-space: nowrap; }
.im-tbl td { padding: 9px 12px; border-bottom: 1px solid var(--border-color); vertical-align: middle; }
.im-tbl tbody tr:last-child td { border-bottom: none; }
.im-tbl tbody tr:hover { background: var(--subtle-fg); }
.im-r { text-align: right; font-variant-numeric: tabular-nums; }
.im-sname { font-weight: 500; }
.im-sid   { font-size: 11px; color: var(--text-muted); }
.im-b { font-size: 11px; font-weight: 600; padding: 3px 9px; border-radius: 12px; white-space: nowrap; }
.im-b--green  { background: #dcfce7; color: #166534; }
.im-b--orange { background: #fef3c7; color: #92400e; }
.im-b--red    { background: #fee2e2; color: #991b1b; }
.im-link { font-size: 15px; color: var(--text-muted); text-decoration: none; }
.im-link:hover { color: var(--primary); }
.im-empty { text-align: center; padding: 48px 20px; color: var(--text-muted); font-size: 14px; }
	`;
	document.head.appendChild(s);
}
