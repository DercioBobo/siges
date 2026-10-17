// Saúde Financeira — left sidebar of checks (with counts), right side the
// selected check's rows. Fixable checks get a per-row button and a
// "Corrigir todos" that runs in small batches with a progress bar.

const FH_API = "escola.escola.page.finance_health.finance_health";
const FH_BATCH = 20;
const FH_GROUP_ICON = { "Dados incorrectos": "🛠️", "Atenção": "👀" };

frappe.pages["finance-health"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Saúde Financeira"),
		single_column: true,
	});
	const fh = new FinanceHealth(page);
	page.add_button(__("Actualizar"), () => fh.refresh(), { icon: "refresh" });
};

class FinanceHealth {
	constructor(page) {
		this.page = page;
		this.$body = $(page.body);
		this.current = null;
		this.rows = [];
		this.can_fix = false;
		_fh_styles();
		this.$body.html(`
		<div class="fh-wrap">
			<aside class="fh-side" id="fh-side"><div class="fh-muted">${__("A analisar…")}</div></aside>
			<main class="fh-main" id="fh-main"></main>
		</div>`);
		this._bind();
		this.refresh();
	}

	_bind() {
		this.$body.on("click", ".fh-item", (e) => this.open($(e.currentTarget).attr("data-key")));
		this.$body.on("click", ".fh-seg-btn", (e) => {
			this._side_view($(e.currentTarget).attr("data-view"));
			this._render_side();
		});
		this.$body.on("click", ".fh-show-all", () => {
			this._side_view("all");
			this._render_side();
		});
		this.$body.on("click", ".fh-student", (e) => {
			e.preventDefault();
			escola.utils.open_student_statement($(e.currentTarget).attr("data-student"));
		});
		this.$body.on("click", ".fh-fix", (e) => {
			const row = this.rows[+$(e.currentTarget).attr("data-idx")];
			if (row) this._confirm_fix([row]);
		});
		this.$body.on("click", "#fh-fix-all", () => {
			this._confirm_fix(this.rows.filter((r) => r.ref));
		});
	}

	async refresh() {
		const r = await frappe.call({ method: `${FH_API}.get_overview` });
		if (!r.message) return;
		this.can_fix = r.message.can_fix;
		this.checks = r.message.checks;
		this._render_side();
		const first = this.current || (this.checks.find((c) => c.count) || this.checks[0]).key;
		this.open(first);
	}

	_render_side() {
		const esc = frappe.utils.escape_html;
		const only_problems = this._side_view() === "problems";
		const problems = this.checks.filter((c) => c.count !== 0).length;

		const groups = {};
		this.checks.forEach((c) => (groups[c.group] = groups[c.group] || []).push(c));

		// count == null means the check itself failed — always shown, never "ok"
		const badge = (c) => c.count === 0
			? `<span class="fh-badge fh-badge--ok">✓</span>`
			: `<span class="fh-badge fh-badge--${c.count == null ? "danger" : c.severity}">${c.count == null ? "!" : c.count}</span>`;

		const card = (c) => `
			<div class="fh-item ${c.key === this.current ? "fh-item--active" : ""}" data-key="${c.key}">
				${badge(c)}
				<div class="fh-item-txt">
					<div class="fh-item-lbl">${esc(c.label)}</div>
					${c.count && c.fixable && this.can_fix ? `<div class="fh-item-sub">${__("correcção rápida disponível")}</div>` : ""}
					${c.count == null ? `<div class="fh-item-sub">${__("erro ao analisar")}</div>` : ""}
				</div>
			</div>`;

		const html = Object.entries(groups).map(([group, checks]) => {
			const total = checks.reduce((s, c) => s + (c.count || 0), 0);
			// keep the open check visible even when it has nothing left
			const visible = only_problems ? checks.filter((c) => c.count !== 0 || c.key === this.current) : checks;
			const hidden = checks.length - visible.length;
			return `
			<div class="fh-group">
				<span>${FH_GROUP_ICON[group] || ""} ${esc(__(group))}</span>
				<span class="fh-group-total ${total ? "" : "fh-group-total--ok"}">${total || "✓"}</span>
			</div>
			${visible.map(card).join("")}
			${!visible.length ? `<div class="fh-allok">✓ ${__("Tudo em ordem")}</div>` : ""}
			${hidden ? `<a class="fh-show-all">${__("+ {0} sem problemas", [hidden])}</a>` : ""}`;
		}).join("");

		this.$body.find("#fh-side").html(`
			<div class="fh-seg">
				<button class="fh-seg-btn ${only_problems ? "active" : ""}" data-view="problems">
					${__("Com problemas")} <span>${problems}</span></button>
				<button class="fh-seg-btn ${only_problems ? "" : "active"}" data-view="all">
					${__("Todos")} <span>${this.checks.length}</span></button>
			</div>
			${html}`);
	}

	_side_view(set) {
		// Per-viewer preference; falls back to "problems" when storage is unavailable
		try {
			if (set) localStorage.setItem("fh_side_view", set);
			return localStorage.getItem("fh_side_view") || "problems";
		} catch (e) {
			if (set) this._view = set;
			return this._view || "problems";
		}
	}

	async open(key) {
		this.current = key;
		this.$body.find(".fh-item").removeClass("fh-item--active");
		this.$body.find(`.fh-item[data-key="${key}"]`).addClass("fh-item--active");
		const $main = this.$body.find("#fh-main").html(`<div class="fh-muted">${__("A carregar…")}</div>`);

		const r = await frappe.call({ method: `${FH_API}.get_check`, args: { key } });
		if (this.current !== key || !r.message) return; // user clicked another check meanwhile
		const { check, rows } = r.message;
		this.rows = rows;
		this.check = check;

		// keep the sidebar count in sync with what we just loaded
		const c = this.checks.find((x) => x.key === key);
		if (c && c.count !== check.count) { c.count = check.count; this._render_side(); }

		const fixable_rows = rows.filter((x) => x.ref).length;
		const fix_all = check.fixable && this.can_fix && fixable_rows
			? `<button class="btn btn-sm btn-primary" id="fh-fix-all">${__("Corrigir todos")} (${fixable_rows})</button>`
			: "";
		const total = rows.reduce((s, x) => s + flt(x.amount), 0);

		$main.html(`
			<div class="fh-head">
				<div>
					<div class="fh-title">${frappe.utils.escape_html(check.label)}</div>
					<div class="fh-desc">${frappe.utils.escape_html(check.description)}</div>
					<div class="fh-stats">${__("{0} registo(s)", [rows.length])}
						${total ? ` · ${__("Valor")}: <b>${format_currency(total)}</b>` : ""}
						${check.fixable ? "" : ` · <span class="fh-tag">${__("Só informativo")}</span>`}
					</div>
				</div>
				${fix_all}
			</div>
			${rows.length ? this._table(rows, check) : `
				<div class="fh-empty">✓ ${__("Nada a assinalar.")}</div>`}`);
	}

	_table(rows, check) {
		const esc = frappe.utils.escape_html;
		const doc_link = ([dt, name]) =>
			`<a href="/app/${frappe.router.slug(dt)}/${encodeURIComponent(name)}" target="_blank">${esc(name)}</a>`;
		const body = rows.map((r, i) => `
			<tr>
				<td>
					<a class="fh-student" data-student="${esc(r.student || "")}">${esc(r.student_name || r.student || "—")}</a>
					<div class="fh-sub">${esc(r.student || "")}</div>
				</td>
				<td class="fh-nw">${esc(r.turma || "—")}</td>
				<td class="fh-docs">${(r.docs || []).map(doc_link).join("<br>")}</td>
				<td class="fh-r fh-nw">${r.amount ? format_number(r.amount, null, 2) : "—"}</td>
				<td class="fh-detail">${esc(r.detail || "")}</td>
				<td class="fh-nw">${check.fixable && this.can_fix && r.ref
					? `<button class="btn btn-xs btn-default fh-fix" data-idx="${i}">${esc(check.fix_label)}</button>`
					: ""}</td>
			</tr>`).join("");
		return `
		<div class="fh-tbl-wrap"><table class="fh-tbl">
			<thead><tr>
				<th>${__("Aluno")}</th><th>${__("Turma")}</th><th>${__("Documentos")}</th>
				<th class="fh-r">${__("Valor")}</th><th>${__("Detalhe")}</th><th></th>
			</tr></thead>
			<tbody>${body}</tbody>
		</table></div>`;
	}

	_confirm_fix(rows) {
		if (!rows.length) return;
		const check = this.check;
		const msg = rows.length === 1
			? __("Aplicar «{0}» a {1}?", [check.fix_label, frappe.utils.escape_html(rows[0].student_name || rows[0].ref)])
			: __("Aplicar «{0}» a {1} registo(s)? Esta operação não pode ser desfeita.", [check.fix_label, rows.length]);
		frappe.confirm(msg, () => this._run_fix(rows.map((r) => r.ref)));
	}

	async _run_fix(refs) {
		const key = this.current;
		let done = 0;
		const errors = [];
		for (let i = 0; i < refs.length; i += FH_BATCH) {
			if (refs.length > FH_BATCH) {
				frappe.show_progress(__("A corrigir…"), i, refs.length, __("{0} de {1}", [i, refs.length]));
			}
			const r = await frappe.call({
				method: `${FH_API}.apply_fix`,
				args: { key, refs: refs.slice(i, i + FH_BATCH) },
			}).catch(() => null);
			if (!r || !r.message) { errors.push(__("Falha de comunicação no lote {0}", [i / FH_BATCH + 1])); continue; }
			done += r.message.done;
			errors.push(...r.message.errors);
		}
		frappe.hide_progress();

		if (errors.length) {
			frappe.msgprint({
				title: __("Corrigidos: {0} · Erros: {1}", [done, errors.length]),
				message: errors.map(frappe.utils.escape_html).join("<br>"),
				indicator: "orange",
			});
		} else {
			frappe.show_alert({ message: __("{0} registo(s) corrigido(s).", [done]), indicator: "green" });
		}
		this.refresh();
	}
}

function _fh_styles() {
	if (document.getElementById("fh-css")) return;
	const s = document.createElement("style");
	s.id = "fh-css";
	s.textContent = `
.fh-wrap { display: flex; gap: 16px; padding: 16px 20px; align-items: flex-start; }
.fh-side { width: 300px; flex-shrink: 0; position: sticky; top: 70px;
	max-height: calc(100vh - 90px); overflow-y: auto; padding-right: 4px; }
.fh-main { flex: 1; min-width: 0; }

/* Com problemas | Todos */
.fh-seg { display: flex; background: var(--subtle-fg); border-radius: 8px; padding: 3px; margin-bottom: 12px; }
.fh-seg-btn { flex: 1; border: none; background: transparent; border-radius: 6px; padding: 6px 8px;
	font-size: 12px; font-weight: 600; color: var(--text-muted); cursor: pointer; }
.fh-seg-btn span { font-weight: 700; opacity: .7; margin-left: 2px; }
.fh-seg-btn.active { background: var(--fg-color); color: var(--text-color); box-shadow: 0 1px 2px rgba(0,0,0,.08); }

.fh-group { display: flex; justify-content: space-between; align-items: center; font-size: 12px; font-weight: 700;
	color: var(--text-muted); text-transform: uppercase; letter-spacing: .5px; padding: 12px 4px 8px; }
.fh-group-total { font-size: 12px; font-weight: 700; padding: 1px 9px; border-radius: 10px;
	background: #fee2e2; color: #dc2626; text-transform: none; letter-spacing: 0; }
.fh-group-total--ok { background: #dcfce7; color: #16a34a; }

.fh-item { display: flex; align-items: center; gap: 14px; padding: 12px 14px; margin-bottom: 8px;
	background: var(--fg-color); border: 1px solid var(--border-color); border-radius: 10px;
	cursor: pointer; transition: border-color .12s, box-shadow .12s; }
.fh-item:hover { border-color: var(--gray-400, #9ca3af); }
.fh-item--active { border-color: var(--primary); box-shadow: 0 0 0 1px var(--primary); }
.fh-badge { min-width: 46px; height: 34px; padding: 0 8px; border-radius: 8px; flex-shrink: 0;
	display: flex; align-items: center; justify-content: center; font-size: 15px; font-weight: 700;
	font-variant-numeric: tabular-nums; }
.fh-badge--danger  { background: #fee2e2; color: #dc2626; }
.fh-badge--warning { background: #fef3c7; color: #b45309; }
.fh-badge--info    { background: #dbeafe; color: #1d4ed8; }
.fh-badge--ok      { background: #dcfce7; color: #16a34a; font-size: 14px; }
.fh-item-txt { flex: 1; min-width: 0; }
.fh-item-lbl { font-size: 14px; font-weight: 600; line-height: 1.3; color: var(--text-color); }
.fh-item-sub { font-size: 12px; color: var(--text-muted); margin-top: 2px; }
.fh-allok { font-size: 12px; color: #16a34a; padding: 4px 4px 8px; }
.fh-show-all { display: block; font-size: 12px; color: var(--text-muted); padding: 0 4px 6px; cursor: pointer; }
.fh-show-all:hover { color: var(--primary); }
.fh-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px;
	background: var(--fg-color); border: 1px solid var(--border-color); border-radius: 10px;
	padding: 14px 16px; margin-bottom: 12px; }
.fh-title { font-size: 16px; font-weight: 600; }
.fh-desc { font-size: 13px; color: var(--text-muted); margin-top: 4px; max-width: 720px; }
.fh-stats { font-size: 12px; color: var(--text-muted); margin-top: 8px; }
.fh-tag { background: var(--subtle-fg); padding: 1px 8px; border-radius: 10px; }
.fh-empty, .fh-muted { padding: 30px; text-align: center; color: var(--text-muted); }
.fh-empty { background: var(--fg-color); border: 1px solid var(--border-color); border-radius: 10px; color: #059669; }
.fh-tbl-wrap { border: 1px solid var(--border-color); border-radius: 10px; overflow-x: auto; background: var(--fg-color); }
.fh-tbl { width: 100%; border-collapse: collapse; font-size: 13px; }
.fh-tbl th { padding: 9px 12px; text-align: left; font-size: 11px; font-weight: 700; color: var(--text-muted);
	text-transform: uppercase; letter-spacing: .5px; background: var(--subtle-fg); }
.fh-tbl td { padding: 9px 12px; border-top: 1px solid var(--border-color); vertical-align: top; }
.fh-r { text-align: right; font-variant-numeric: tabular-nums; }
.fh-nw { white-space: nowrap; }
.fh-sub { font-size: 11px; color: var(--text-muted); }
.fh-student { font-weight: 500; cursor: pointer; color: var(--text-color); }
.fh-student:hover { color: var(--primary); text-decoration: underline; }
.fh-docs { font-size: 12px; white-space: nowrap; }
.fh-detail { font-size: 12px; color: var(--text-muted); min-width: 220px; }
@media (max-width: 900px) {
	.fh-wrap { flex-direction: column; }
	.fh-side { width: 100%; position: static; max-height: none; overflow: visible; }
}`;
	document.head.appendChild(s);
}
