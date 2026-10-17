// Impressões do Aluno — pick a student, click a tile, the document prints.
// Documents themselves live in public/js/escola_print.js (escola.print.*),
// shared with the Student form.

const IMP_API = "escola.escola.page.impressoes_aluno.impressoes_aluno";

frappe.pages["impressoes-aluno"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Impressões do Aluno"),
		single_column: true,
	});
	wrapper._imp = new StudentPrints(page);
};

frappe.pages["impressoes-aluno"].on_page_show = function (wrapper) {
	const opts = frappe.route_options || {};
	frappe.route_options = null;
	if (opts.student && wrapper._imp) wrapper._imp.set_student(opts.student);
};

class StudentPrints {
	constructor(page) {
		this.page = page;
		_imp_styles();

		this.f_student = page.add_field({
			fieldname: "student",
			fieldtype: "Link",
			options: "Student",
			label: __("Aluno"),
			change: () => this.load(this.f_student.get_value()),
		});

		// Never replace page.body wholesale — page_form (the field above) lives in it.
		this.$content = $(`<div class="imp-wrap"></div>`).appendTo(page.body);
		this.$content.html(this._empty(__("Pesquise um aluno para ver o que pode imprimir.")));

		this.$content.on("click", "[data-print]", (e) => this._print($(e.currentTarget)));
		this.$content.on("click", ".imp-toggle", (e) => {
			$(e.currentTarget).closest(".imp-tile").toggleClass("imp-open");
		});
	}

	set_student(student) {
		if (this.f_student.get_value() === student) this.load(student);
		else this.f_student.set_value(student); // change() → load()
	}

	async load(student) {
		this.student = student;
		if (!student) {
			this.$content.html(this._empty(__("Pesquise um aluno para ver o que pode imprimir.")));
			return;
		}
		this.$content.html(this._empty(__("A carregar…")));
		const r = await frappe.call({ method: `${IMP_API}.get_hub`, args: { student } }).catch(() => null);
		if (this.student !== student) return; // another student was picked meanwhile
		if (!r || !r.message) {
			this.$content.html(this._empty(__("Não foi possível carregar o aluno.")));
			return;
		}
		this.data = r.message;
		this._render();
	}

	_render() {
		const { student: st, can_see_finance, report_cards, invoices, payments } = this.data;
		const esc = frappe.utils.escape_html;
		const num = (v) => format_number(flt(v), null, 2);
		const dt = (v) => (v ? frappe.datetime.str_to_user(v) : "");

		const card = `
		<div class="imp-card">
			<div class="imp-avatar">${esc((st.full_name || "?").trim().charAt(0).toUpperCase())}</div>
			<div class="imp-card-main">
				<div class="imp-name">${esc(st.full_name)} <span class="imp-code">${esc(st.student_code || "")}</span></div>
				<div class="imp-meta">
					${esc([st.class_name, st.turma_name].filter(Boolean).join(" · ") || __("Sem turma"))}
					· ${esc(st.current_status || "—")}
					${can_see_finance && st.financial_status ? ` · ${__("Situação financeira")}: <b>${esc(st.financial_status)}</b>` : ""}
				</div>
			</div>
			<a class="btn btn-xs btn-default" href="/app/student/${encodeURIComponent(st.name)}">${__("Abrir ficha")}</a>
		</div>`;

		// A tile either prints straight away (data-print on the tile) or opens
		// a list of items, each with its own print button.
		const tile = ({ icon, title, desc, action, list, disabled }) => `
		<div class="imp-tile ${list ? "imp-has-list" : ""} ${disabled ? "imp-disabled" : ""}">
			<div class="imp-tile-head ${list ? "imp-toggle" : ""}" ${!list && !disabled ? `data-print="${action}"` : ""}>
				<div class="imp-icon">${icon}</div>
				<div class="imp-tile-txt">
					<div class="imp-tile-title">${title}</div>
					<div class="imp-tile-desc">${desc}</div>
				</div>
				<div class="imp-go">${list ? "▾" : "🖨"}</div>
			</div>
			${list ? `<div class="imp-list">${list}</div>` : ""}
		</div>`;

		const item = (label, sub, attrs) => `
			<div class="imp-item">
				<div><div>${label}</div><div class="imp-sub">${sub}</div></div>
				<button class="btn btn-xs btn-default" ${attrs}>${__("Imprimir")}</button>
			</div>`;
		const empty_list = (msg) => `<div class="imp-sub" style="padding:8px 4px;">${msg}</div>`;

		const has_turma = !!st.current_class_group;

		const academic = [
			tile({
				icon: "📄", title: __("Declaração de Matrícula"), action: "declaracao", disabled: !has_turma,
				desc: has_turma ? __("Declaração oficial de que o aluno está matriculado e a frequentar a turma.")
					: __("Indisponível — o aluno não tem turma activa."),
			}),
			tile({
				icon: "🪪", title: __("Ficha do Aluno"), action: "ficha",
				desc: __("Identificação, encarregado, matrícula, percurso académico e documentos."),
			}),
			tile({
				icon: "🎓", title: __("Boletim Anual"),
				desc: __("{0} boletim(ns) emitido(s)", [report_cards.length]),
				list: report_cards.length
					? report_cards.map((rc) => item(
						esc(rc.academic_year),
						esc([rc.school_class, rc.overall_average != null ? __("Média {0}", [flt(rc.overall_average).toFixed(1)]) : "",
							rc.final_decision].filter(Boolean).join(" · ")),
						`data-print="doc" data-doctype="Report Card" data-name="${esc(rc.name)}" data-format="Boletim"`,
					)).join("")
					: empty_list(__("Ainda não há boletins emitidos. Use o «Boletim em curso».")),
			}),
			tile({
				icon: "📊", title: __("Boletim em curso"), action: "boletim-page",
				desc: __("Notas do ano/período actual na página Boletim do Aluno, pronta a imprimir."),
			}),
		];

		const finance = !can_see_finance ? [] : [
			tile({
				icon: "💳", title: __("Extrato de Conta"), action: "extrato",
				desc: __("Todas as facturas e pagamentos, com o saldo em dívida."),
			}),
			tile({
				icon: "🧾", title: __("Recibos"),
				desc: __("{0} pagamento(s)", [payments.length]),
				list: payments.length
					? payments.map((p) => item(
						`${esc(p.name)} · <b>${num(p.amount)}</b>`,
						esc([dt(p.posting_date), p.mode_of_payment, p.invoice].filter(Boolean).join(" · ")),
						`data-print="doc" data-doctype="${esc(p.doctype)}" data-name="${esc(p.name)}"`,
					)).join("")
					: empty_list(__("Sem pagamentos registados.")),
			}),
			tile({
				icon: "📑", title: __("Facturas"),
				desc: __("{0} factura(s)", [invoices.length]),
				list: invoices.length
					? invoices.map((i) => item(
						`${esc(i.name)} · <b>${num(i.grand_total)}</b>`,
						esc([dt(i.posting_date), i.tipo, i.docstatus === 0 ? __("Rascunho")
							: flt(i.outstanding_amount) > 0 ? __("Em dívida {0}", [num(i.outstanding_amount)]) : __("Paga")]
							.filter(Boolean).join(" · ")),
						`data-print="doc" data-doctype="Sales Invoice" data-name="${esc(i.name)}"`,
					)).join("")
					: empty_list(__("Sem facturas.")),
			}),
		];

		this.$content.html(`
			${card}
			<div class="imp-group">${__("Académico")}</div>
			<div class="imp-grid">${academic.join("")}</div>
			${finance.length ? `
				<div class="imp-group">${__("Financeiro")}</div>
				<div class="imp-grid">${finance.join("")}</div>` : ""}
		`);
	}

	_print($el) {
		const what = $el.attr("data-print");
		const student = this.student;
		switch (what) {
			case "extrato":    escola.print.extrato(student); break;
			case "declaracao": escola.print.declaracao(student); break;
			case "ficha":      escola.print.ficha(student); break;
			case "doc":
				escola.print.doc($el.attr("data-doctype"), $el.attr("data-name"), $el.attr("data-format"));
				break;
			case "boletim-page":
				frappe.route_options = { student };
				frappe.set_route("boletim-aluno");
				break;
		}
	}

	_empty(msg) {
		return `<div class="imp-empty">${msg}</div>`;
	}
}

function _imp_styles() {
	if (document.getElementById("imp-css")) return;
	const s = document.createElement("style");
	s.id = "imp-css";
	s.textContent = `
.imp-wrap { padding: 4px 4px 24px; max-width: 1100px; }
.imp-empty { padding: 50px 20px; text-align: center; color: var(--text-muted); }
.imp-card { display: flex; align-items: center; gap: 14px; background: var(--fg-color);
	border: 1px solid var(--border-color); border-radius: 10px; padding: 14px 16px; margin-bottom: 18px; }
.imp-avatar { width: 46px; height: 46px; border-radius: 50%; background: var(--primary); color: #fff;
	display: flex; align-items: center; justify-content: center; font-size: 20px; font-weight: 600; flex-shrink: 0; }
.imp-card-main { flex: 1; min-width: 0; }
.imp-name { font-size: 16px; font-weight: 600; }
.imp-code { font-size: 12px; font-weight: 400; color: var(--text-muted); margin-left: 6px; }
.imp-meta { font-size: 12px; color: var(--text-muted); margin-top: 3px; }
.imp-group { font-size: 11px; font-weight: 700; color: var(--text-muted); text-transform: uppercase;
	letter-spacing: .5px; margin: 6px 0 8px; }
.imp-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 12px;
	margin-bottom: 20px; align-items: start; }
.imp-tile { background: var(--fg-color); border: 1px solid var(--border-color); border-radius: 10px;
	overflow: hidden; transition: border-color .12s, box-shadow .12s; }
.imp-tile:not(.imp-disabled):hover { border-color: var(--primary); box-shadow: 0 2px 8px rgba(0,0,0,.06); }
.imp-tile-head { display: flex; gap: 12px; align-items: flex-start; padding: 14px; cursor: pointer; }
.imp-disabled { opacity: .55; }
.imp-disabled .imp-tile-head { cursor: not-allowed; }
.imp-icon { font-size: 22px; line-height: 1; }
.imp-tile-txt { flex: 1; min-width: 0; }
.imp-tile-title { font-weight: 600; font-size: 14px; }
.imp-tile-desc { font-size: 12px; color: var(--text-muted); margin-top: 3px; }
.imp-go { color: var(--text-muted); font-size: 14px; transition: transform .15s; }
.imp-open .imp-go { transform: rotate(180deg); }
.imp-list { display: none; border-top: 1px solid var(--border-color); max-height: 320px; overflow-y: auto; padding: 4px 10px; }
.imp-open .imp-list { display: block; }
.imp-item { display: flex; justify-content: space-between; align-items: center; gap: 10px;
	padding: 7px 4px; border-bottom: 1px solid var(--border-color); font-size: 12px; }
.imp-item:last-child { border-bottom: none; }
.imp-sub { font-size: 11px; color: var(--text-muted); }
@media (max-width: 600px) { .imp-card { flex-wrap: wrap; } }`;
	document.head.appendChild(s);
}
