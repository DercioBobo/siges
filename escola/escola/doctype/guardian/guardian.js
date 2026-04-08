// Copyright (c) 2024, EntreTech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Guardian", {
	first_name(frm) { _update_full_name(frm); },
	last_name(frm)  { _update_full_name(frm); },

	refresh(frm) {
		_gd_styles();
		if (!frm.is_new()) {
			_render_students(frm);
		} else {
			frm.fields_dict.students_html.$wrapper.html(
				`<div class="gd-empty">Guarde o registo para associar educandos.</div>`
			);
		}
	},
});

function _update_full_name(frm) {
	const parts = [frm.doc.first_name, frm.doc.last_name].filter(Boolean);
	frm.set_value("full_name", parts.join(" "));
}

// ---------------------------------------------------------------------------
// Student panel
// ---------------------------------------------------------------------------

async function _render_students(frm) {
	const $wrap = frm.fields_dict.students_html.$wrapper;
	$wrap.html(`<div class="gd-loading">A carregar…</div>`);

	const r = await frappe.call({
		method: "escola.escola.doctype.guardian.guardian.get_students",
		args: { guardian: frm.doc.name },
	});

	const students = r.message || [];
	$wrap.empty();

	// Cards
	if (!students.length) {
		$wrap.append(`<div class="gd-empty">Nenhum educando associado ainda.</div>`);
	} else {
		const $list = $(`<div class="gd-list"></div>`).appendTo($wrap);
		students.forEach(s => {
			const statusCls = {
				"Activo": "gd-st--green",
				"Transferido": "gd-st--blue",
				"Desistente": "gd-st--red",
				"Concluiu": "gd-st--grey",
			}[s.current_status] || "";

			const finCls = s.financial_status === "Regular" ? "gd-fin--ok" : "gd-fin--warn";

			const $card = $(`
				<div class="gd-card">
					<div class="gd-card-body">
						<div class="gd-card-avatar">${(s.full_name || "?")[0].toUpperCase()}</div>
						<div class="gd-card-info">
							<div class="gd-card-name">${frappe.utils.escape_html(s.full_name)}</div>
							<div class="gd-card-meta">
								${s.student_code ? `<span>${frappe.utils.escape_html(s.student_code)}</span>` : ""}
								${s.current_class_group ? `<span>${frappe.utils.escape_html(s.current_class_group)}</span>` : ""}
								<span class="gd-st ${statusCls}">${s.current_status || "—"}</span>
								${s.financial_status ? `<span class="gd-fin ${finCls}">${s.financial_status}</span>` : ""}
							</div>
						</div>
					</div>
					<div class="gd-card-actions">
						<button class="btn btn-xs btn-default gd-btn-open" data-student="${s.name}" title="Abrir ficha">
							<i class="fa fa-external-link"></i>
						</button>
						<button class="btn btn-xs btn-danger gd-btn-remove" data-student="${s.name}" title="Remover ligação">
							<i class="fa fa-unlink"></i>
						</button>
					</div>
				</div>
			`).appendTo($list);

			$card.find(".gd-btn-open").on("click", function () {
				frappe.set_route("Form", "Student", $(this).data("student"));
			});

			$card.find(".gd-btn-remove").on("click", async function () {
				const student = $(this).data("student");
				const name = frappe.utils.escape_html(s.full_name);
				frappe.confirm(
					`Remover a ligação de <b>${name}</b> a este encarregado?`,
					async () => {
						await frappe.call({
							method: "escola.escola.doctype.guardian.guardian.remove_student",
							args: { guardian: frm.doc.name, student },
						});
						_render_students(frm);
					}
				);
			});
		});
	}

	// Add button
	$(`<button class="btn btn-sm btn-primary gd-btn-add" style="margin-top:14px;">
		<i class="fa fa-plus"></i>&nbsp;Adicionar Educando
	</button>`).appendTo($wrap).on("click", () => _open_assign_dialog(frm));
}

// ---------------------------------------------------------------------------
// Assign dialog
// ---------------------------------------------------------------------------

function _open_assign_dialog(frm) {
	const d = new frappe.ui.Dialog({
		title: __("Adicionar Educando"),
		fields: [
			{
				fieldtype: "Data",
				fieldname: "search",
				label: "Pesquisar (nome ou número de aluno)",
				placeholder: "Digite para pesquisar…",
			},
			{ fieldtype: "HTML", fieldname: "results_html" },
		],
		primary_action_label: __("Associar Seleccionados"),
		async primary_action() {
			const selected = d.$wrapper.find(".gd-chk:checked")
				.map(function () { return $(this).val(); }).get();
			if (!selected.length) {
				frappe.msgprint(__("Seleccione pelo menos um aluno."));
				return;
			}
			await frappe.call({
				method: "escola.escola.doctype.guardian.guardian.assign_students",
				args: { guardian: frm.doc.name, students: selected },
			});
			d.hide();
			_render_students(frm);
		},
	});

	d.show();

	const $results = d.fields_dict.results_html.$wrapper;

	async function _search(q) {
		$results.html(`<div class="gd-loading" style="padding:8px 0;">A pesquisar…</div>`);
		const r = await frappe.call({
			method: "escola.escola.doctype.guardian.guardian.search_students",
			args: { query: q, exclude_guardian: frm.doc.name },
		});
		const rows = r.message || [];
		if (!rows.length) {
			$results.html(`<div class="gd-empty" style="padding:8px 0;">Nenhum aluno encontrado.</div>`);
			return;
		}
		$results.empty();
		const $list = $(`<div class="gd-pick-list"></div>`).appendTo($results);
		rows.forEach(s => {
			const already = s.primary_guardian && s.primary_guardian !== frm.doc.name;
			$(`
				<label class="gd-pick-row ${already ? "gd-pick-row--taken" : ""}">
					<input type="checkbox" class="gd-chk" value="${s.name}" ${already ? "disabled" : ""}>
					<div class="gd-pick-info">
						<div class="gd-card-name">${frappe.utils.escape_html(s.full_name)}</div>
						<div class="gd-card-meta">
							${s.student_code ? `<span>${frappe.utils.escape_html(s.student_code)}</span>` : ""}
							${s.current_class_group ? `<span>${frappe.utils.escape_html(s.current_class_group)}</span>` : ""}
							${already ? `<span class="gd-taken">já tem encarregado</span>` : ""}
						</div>
					</div>
				</label>
			`).appendTo($list);
		});
	}

	_search("");

	let _debounce;
	d.fields_dict.search.$input.on("input", function () {
		clearTimeout(_debounce);
		_debounce = setTimeout(() => _search($(this).val().trim()), 300);
	});
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

function _gd_styles() {
	if (document.getElementById("gd-css")) return;
	const s = document.createElement("style");
	s.id = "gd-css";
	s.textContent = `
/* Cards */
.gd-list { display: flex; flex-direction: column; gap: 8px; }
.gd-card { display: flex; align-items: center; justify-content: space-between;
	gap: 12px; background: var(--fg-color); border: 1.5px solid var(--border-color);
	border-radius: 10px; padding: 10px 14px; transition: border-color .15s; }
.gd-card:hover { border-color: var(--primary); }
.gd-card-body { display: flex; align-items: center; gap: 12px; flex: 1; min-width: 0; }
.gd-card-avatar { width: 38px; height: 38px; border-radius: 50%;
	background: var(--primary); color: white; display: flex; align-items: center;
	justify-content: center; font-size: 16px; font-weight: 700; flex-shrink: 0; }
.gd-card-info { min-width: 0; }
.gd-card-name { font-size: 14px; font-weight: 600; color: var(--text-color);
	white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.gd-card-meta { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 3px; font-size: 12px;
	color: var(--text-muted); }
.gd-card-meta span { background: var(--subtle-fg); padding: 1px 7px; border-radius: 10px; }
.gd-card-actions { display: flex; gap: 6px; flex-shrink: 0; }

/* Status badges */
.gd-st { font-weight: 600 !important; }
.gd-st--green  { background: #dcfce7 !important; color: #166534 !important; }
.gd-st--blue   { background: #dbeafe !important; color: #1d4ed8 !important; }
.gd-st--red    { background: #fee2e2 !important; color: #991b1b !important; }
.gd-st--grey   { background: #f3f4f6 !important; color: #6b7280 !important; }
.gd-fin--ok    { background: #d1fae5 !important; color: #065f46 !important; }
.gd-fin--warn  { background: #fef3c7 !important; color: #92400e !important; }

/* Empty / loading */
.gd-empty   { color: var(--text-muted); font-size: 13px; padding: 12px 2px; }
.gd-loading { color: var(--text-muted); font-size: 13px; }

/* Pick list (assign dialog) */
.gd-pick-list { display: flex; flex-direction: column; gap: 4px;
	max-height: 320px; overflow-y: auto; margin-top: 6px; }
.gd-pick-row { display: flex; align-items: center; gap: 10px; padding: 8px 10px;
	border-radius: 8px; cursor: pointer; border: 1.5px solid transparent;
	transition: background .12s; }
.gd-pick-row:hover { background: var(--subtle-fg); }
.gd-pick-row input[type=checkbox] { flex-shrink: 0; width: 16px; height: 16px; cursor: pointer; }
.gd-pick-row--taken { opacity: .5; cursor: default; }
.gd-pick-info { min-width: 0; }
.gd-taken { color: var(--orange-500) !important; font-style: italic; }
	`;
	document.head.appendChild(s);
}
