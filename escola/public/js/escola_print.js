window.escola = window.escola || {};

// ---------------------------------------------------------------------------
// Printable student documents, shared by the Student form ("Imprimir
// Extrato") and the "Impressões do Aluno" page. Each document is a full HTML
// page written into a new tab that prints itself on load.
//
//   escola.print.extrato(student)
//   escola.print.declaracao(student)
//   escola.print.ficha(student)
// ---------------------------------------------------------------------------

escola.print = (function () {
	const MESES = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
		"Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"];

	const esc = (v) => frappe.utils.escape_html(v == null ? "" : String(v));
	const num = (v) => format_number(flt(v), null, 2);
	const dt = (v) => (v ? frappe.datetime.str_to_user(v) : "—");

	function date_in_words(d) {
		const x = frappe.datetime.str_to_obj(d || frappe.datetime.get_today());
		return `${x.getDate()} de ${MESES[x.getMonth()]} de ${x.getFullYear()}`;
	}

	/**
	 * Open the print tab synchronously (browsers block window.open() after an
	 * await), then fill it with the HTML that `build` resolves to.
	 */
	async function open(build) {
		const w = window.open("", "_blank");
		if (!w) {
			frappe.msgprint(__("O navegador bloqueou a janela de impressão. Permita pop-ups para este site."));
			return;
		}
		w.document.write(`<p style="font-family:sans-serif;padding:20px">${__("A preparar documento…")}</p>`);
		try {
			const html = await build();
			if (!html) { w.close(); return; }
			w.document.open();
			w.document.write(html);
			w.document.close();
		} catch (e) {
			w.close();
			if (e && e.message) frappe.msgprint(e.message);
		}
	}

	/** A4 page with the school letterhead; prints itself once loaded. */
	function shell({ school, title, doc_title, body, css = "" }) {
		const sc = school || {};
		const school_lines = [
			sc.school_address,
			[sc.school_nif && `NUIT: ${sc.school_nif}`, sc.school_phone, sc.school_email].filter(Boolean).join(" · "),
		].filter(Boolean).map(esc).join("<br>");

		return `<!DOCTYPE html>
<html lang="pt">
<head>
<meta charset="utf-8">
<title>${esc(doc_title)}</title>
<style>
	@page { size: A4; margin: 14mm 12mm; }
	* { box-sizing: border-box; }
	body { font-family: "Segoe UI", Arial, sans-serif; font-size: 11px; color: #111; margin: 0; }
	.top { display: flex; align-items: center; gap: 14px; border-bottom: 2px solid #111; padding-bottom: 10px; }
	.top img { height: 60px; }
	.school { font-size: 15px; font-weight: 700; }
	.school-sub { font-size: 10px; color: #444; margin-top: 2px; line-height: 1.4; }
	h1 { font-size: 14px; text-align: center; letter-spacing: 1px; margin: 14px 0 10px; }
	h2 { font-size: 11px; text-transform: uppercase; letter-spacing: .5px; margin: 14px 0 5px; }
	.info { display: grid; grid-template-columns: 1fr 1fr; gap: 3px 24px; margin-bottom: 12px; }
	.info b { display: inline-block; min-width: 110px; }
	table { width: 100%; border-collapse: collapse; }
	th, td { border: 1px solid #bbb; padding: 4px 6px; text-align: left; }
	th { background: #eee; font-size: 9.5px; text-transform: uppercase; }
	tr { page-break-inside: avoid; }
	.r { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
	.empty { text-align: center; color: #666; }
	.foot { margin-top: 30px; display: flex; justify-content: space-between; align-items: flex-end; font-size: 10px; color: #444; }
	.sig { width: 220px; border-top: 1px solid #111; text-align: center; padding-top: 4px; }
	${css}
</style>
</head>
<body>
	<div class="top">
		${sc.school_logo ? `<img src="${esc(sc.school_logo)}">` : ""}
		<div>
			<div class="school">${esc(sc.school_name || "")}</div>
			<div class="school-sub">${school_lines}</div>
		</div>
	</div>
	<h1>${esc(title)}</h1>
	${body}
	<script>
		window.onload = function () { setTimeout(function () { window.print(); }, 300); };
	</script>
</body>
</html>`;
	}

	async function call(method, args) {
		const r = await frappe.call({ method, args });
		return r && r.message;
	}

	// -----------------------------------------------------------------------
	// Extrato de Conta
	// -----------------------------------------------------------------------

	const EXTRATO_STATUS = {
		"Rascunho":  "Em Aberto",
		"Paga":      "Paga",
		"Em Atraso": "Vencida",
		"Emitida":   "Em Dívida",
	};

	function extrato_html({ school, student: st, invoices, payments, summary }) {
		const today = dt(frappe.datetime.get_today());

		const inv_rows = invoices.slice().reverse().map((i) => {
			let status = EXTRATO_STATUS[i.status] || i.status;
			if (i.status !== "Paga" && i.status !== "Rascunho" && i.paid > 0) status = "Parcialmente Paga";
			return `<tr>
				<td>${esc(i.name)}</td>
				<td>${esc(i.tipo || "")}</td>
				<td>${esc(i.posting_date)}</td>
				<td>${esc(i.due_date)}</td>
				<td class="r">${num(i.grand_total)}</td>
				<td class="r">${i.multa ? num(i.multa) : "—"}</td>
				<td class="r">${num(i.paid)}</td>
				<td class="r ${i.owed > 0 ? "owed" : ""}">${num(i.owed)}</td>
				<td>${esc(__(status))}</td>
			</tr>`;
		}).join("");

		const pay_rows = payments.slice().reverse().map((p) => `<tr>
				<td>${esc(dt(p.posting_date))}</td>
				<td>${esc(p.name)}</td>
				<td>${esc(p.mode_of_payment || "—")}</td>
				<td>${esc(p.invoice)}</td>
				<td class="r">${num(p.amount)}</td>
			</tr>`).join("");

		const body = `
		<div class="info">
			<div><b>${__("Aluno")}:</b> ${esc(st.full_name)}</div>
			<div><b>${__("Código")}:</b> ${esc(st.student_code || st.name)}</div>
			<div><b>${__("Turma")}:</b> ${esc(st.turma_name || st.current_school_class || "—")}</div>
			<div><b>${__("Estado")}:</b> ${esc(st.current_status || "—")}</div>
			<div><b>${__("Encarregado")}:</b> ${esc(st.primary_guardian || "—")}${st.guardian_phone ? " · " + esc(st.guardian_phone) : ""}</div>
			<div><b>${__("Data de emissão")}:</b> ${esc(today)}</div>
		</div>

		<div class="cards">
			<div class="card"><div class="l">${__("Total facturado")}</div><div class="v">${num(summary.total_invoiced)}</div></div>
			<div class="card"><div class="l">${__("Total pago")}</div><div class="v">${num(summary.total_paid)}</div></div>
			<div class="card owed"><div class="l">${__("Saldo em dívida")}</div><div class="v">${num(summary.total_owed)}</div></div>
		</div>

		<h2>${__("Facturas")} (${invoices.length})</h2>
		<table>
			<thead><tr>
				<th>${__("Factura")}</th><th>${__("Tipo")}</th><th>${__("Emissão")}</th><th>${__("Vencimento")}</th>
				<th class="r">${__("Total")}</th><th class="r">${__("Multa")}</th><th class="r">${__("Pago")}</th>
				<th class="r">${__("Em Dívida")}</th><th>${__("Estado")}</th>
			</tr></thead>
			<tbody>${inv_rows || `<tr><td colspan="9" class="empty">${__("Sem facturas.")}</td></tr>`}</tbody>
		</table>

		<h2>${__("Pagamentos")} (${payments.length})</h2>
		<table>
			<thead><tr>
				<th>${__("Data")}</th><th>${__("Documento")}</th><th>${__("Modo")}</th><th>${__("Factura")}</th><th class="r">${__("Valor")}</th>
			</tr></thead>
			<tbody>${pay_rows || `<tr><td colspan="5" class="empty">${__("Sem pagamentos registados.")}</td></tr>`}</tbody>
		</table>

		<div class="foot">
			<div>${__("Valores em MZN.")} ${__("Documento emitido em {0}.", [esc(today)])}</div>
			<div class="sig">${__("A Tesouraria")}</div>
		</div>`;

		return shell({
			school,
			title: __("EXTRATO DE CONTA DO ALUNO"),
			doc_title: `${__("Extrato")} — ${st.full_name}`,
			body,
			css: `
	.cards { display: flex; gap: 10px; margin-bottom: 14px; }
	.card { flex: 1; border: 1px solid #bbb; border-radius: 4px; padding: 6px 10px; }
	.card .l { font-size: 9px; text-transform: uppercase; color: #555; letter-spacing: .5px; }
	.card .v { font-size: 14px; font-weight: 700; margin-top: 2px; }
	.card.owed .v { color: #b45309; }
	.owed { font-weight: 700; }`,
		});
	}

	// -----------------------------------------------------------------------
	// Declaração de Matrícula
	// -----------------------------------------------------------------------

	function declaracao_html({ school, student: st, enrolment: en, guardian: g }) {
		if (!en) {
			throw new Error(__("O aluno não tem uma turma activa — não é possível emitir a declaração de matrícula."));
		}
		const born = [
			st.date_of_birth && __("nascido(a) a {0}", [esc(date_in_words(st.date_of_birth))]),
			st.place_of_birth && __("em {0}", [esc(st.place_of_birth)]),
		].filter(Boolean).join(" ");
		const parts = [
			`${__("Para os devidos efeitos, declara-se que")} <b>${esc(st.full_name)}</b>`,
			born,
			st.bi_number && __("portador(a) do B.I. n.º {0}", [esc(st.bi_number)]),
			g && g.full_name && __("cujo Encarregado de Educação é {0}", [esc(g.full_name)]),
		].filter(Boolean).join(", ");

		const body = `
		<div class="decl">
			<p>${parts}, ${__("encontra-se regularmente matriculado(a) nesta instituição de ensino no Ano Lectivo")}
				<b>${esc(en.academic_year)}</b>, ${__("a frequentar a")} <b>${esc(en.class_name)}</b>,
				${__("turma")} <b>${esc(en.turma_name)}</b>, ${__("com o número de estudante")}
				<b>${esc(st.student_code || st.name)}</b>.</p>
			<p>${__("Por ser verdade e me ter sido solicitada, passa-se a presente declaração, que vai assinada e autenticada com o carimbo em uso nesta escola.")}</p>
			<p class="date">${esc(date_in_words())}</p>
		</div>
		<div class="foot decl-foot">
			<div></div>
			<div class="sig">${__("A Direcção da Escola")}</div>
		</div>`;

		return shell({
			school,
			title: __("DECLARAÇÃO DE MATRÍCULA"),
			doc_title: `${__("Declaração de Matrícula")} — ${st.full_name}`,
			body,
			css: `
	.decl { font-size: 13px; line-height: 1.9; text-align: justify; margin: 40px 10px 0; }
	.decl p { margin: 0 0 18px; text-indent: 40px; }
	.decl .date { text-align: right; text-indent: 0; margin-top: 40px; }
	.decl-foot { margin-top: 80px; font-size: 12px; }`,
		});
	}

	// -----------------------------------------------------------------------
	// Ficha do Aluno
	// -----------------------------------------------------------------------

	function ficha_html({ school, student: st, enrolment: en, guardian: g, history, documents }) {
		const row = (label, value) => `<div><b>${label}:</b> ${esc(value || "—")}</div>`;

		const hist_rows = (history || []).map((h) => `<tr>
			<td>${esc(h.academic_year)}</td>
			<td>${esc(h.school_class || "—")}</td>
			<td>${esc(h.class_group || "—")}</td>
			<td>${esc(h.sga_status || "—")}</td>
			<td class="r">${h.overall_average != null ? esc(flt(h.overall_average).toFixed(1)) : "—"}</td>
			<td class="r">${h.total_absences != null ? esc(h.total_absences) : "—"}</td>
			<td>${esc(h.final_decision || "—")}</td>
		</tr>`).join("");

		const doc_rows = (documents || []).map((d) => `<tr>
			<td>${esc(d.document_label || d.document_type)}${d.is_required ? " *" : ""}</td>
			<td>${esc(d.status || "—")}</td>
			<td>${esc(dt(d.submitted_date))}</td>
		</tr>`).join("");

		const body = `
		<h2>${__("Identificação")}</h2>
		<div class="info">
			${row(__("Nome completo"), st.full_name)}
			${row(__("Código"), st.student_code || st.name)}
			${row(__("Sexo"), st.gender)}
			${row(__("Data de nascimento"), st.date_of_birth && `${dt(st.date_of_birth)}${st.idade ? ` (${st.idade} ${__("anos")})` : ""}`)}
			${row(__("Naturalidade"), st.place_of_birth)}
			${row(__("B.I. n.º"), st.bi_number)}
			${row(__("Telefone"), st.phone)}
			${row(__("Morada"), st.address)}
		</div>

		<h2>${__("Encarregado de Educação")}</h2>
		<div class="info">
			${row(__("Nome"), g && g.full_name)}
			${row(__("Parentesco"), g && g.relationship)}
			${row(__("Telefone"), g && [g.phone, g.alternative_phone].filter(Boolean).join(" / "))}
			${row(__("Email"), g && g.email)}
			${row(__("Morada"), g && g.address)}
		</div>

		<h2>${__("Matrícula")}</h2>
		<div class="info">
			${row(__("Estado"), st.current_status)}
			${row(__("Data de admissão"), st.admission_date && dt(st.admission_date))}
			${row(__("Ano lectivo"), en && en.academic_year)}
			${row(__("Classe / Turma"), en && `${en.class_name} · ${en.turma_name}`)}
			${row(__("Bolseiro"), st.is_bolsista ? __("Sim") : __("Não"))}
			${st.return_date ? row(__("Data de regresso"), dt(st.return_date)) : ""}
			${st.withdrawal_date ? row(__("Data de desistência"), dt(st.withdrawal_date)) : ""}
		</div>

		<h2>${__("Percurso Académico")}</h2>
		<table>
			<thead><tr>
				<th>${__("Ano")}</th><th>${__("Classe")}</th><th>${__("Turma")}</th><th>${__("Alocação")}</th>
				<th class="r">${__("Média")}</th><th class="r">${__("Faltas")}</th><th>${__("Decisão")}</th>
			</tr></thead>
			<tbody>${hist_rows || `<tr><td colspan="7" class="empty">${__("Sem registos.")}</td></tr>`}</tbody>
		</table>

		<h2>${__("Documentos")}</h2>
		<table>
			<thead><tr><th>${__("Documento")}</th><th>${__("Estado")}</th><th>${__("Entregue em")}</th></tr></thead>
			<tbody>${doc_rows || `<tr><td colspan="3" class="empty">${__("Sem documentos registados.")}</td></tr>`}</tbody>
		</table>
		${doc_rows ? `<div style="font-size:9px;color:#555;margin-top:3px;">* ${__("obrigatório")}</div>` : ""}

		<div class="foot">
			<div>${__("Documento emitido em {0}.", [esc(dt(frappe.datetime.get_today()))])}</div>
			<div class="sig">${__("A Secretaria")}</div>
		</div>`;

		return shell({
			school,
			title: __("FICHA DO ALUNO"),
			doc_title: `${__("Ficha do Aluno")} — ${st.full_name}`,
			body,
		});
	}

	// -----------------------------------------------------------------------
	// Public API
	// -----------------------------------------------------------------------

	const DOC_API = "escola.escola.page.impressoes_aluno.impressoes_aluno.get_document_data";

	return {
		open,
		shell,
		extrato: (student) => open(async () => {
			const data = await call("escola.escola.invoice_query.get_student_statement", { student, full: 1 });
			return data && extrato_html(data);
		}),
		declaracao: (student) => open(async () => {
			const data = await call(DOC_API, { student });
			return data && declaracao_html(data);
		}),
		ficha: (student) => open(async () => {
			const data = await call(DOC_API, { student });
			return data && ficha_html(data);
		}),
		/** Standard Frappe print view of any document, e.g. a Report Card's "Boletim". */
		doc: (doctype, name, format) => {
			const q = new URLSearchParams({ doctype, name, trigger_print: 1 });
			if (format) q.set("format", format);
			window.open(`/printview?${q.toString()}`, "_blank");
		},
	};
})();
