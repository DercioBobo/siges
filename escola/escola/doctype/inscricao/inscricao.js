// Copyright (c) 2024, EntreTech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Inscricao", {
	onload(frm) {
		escola.utils.auto_fill_academic_year(frm);
		_apply_novo_class_filter(frm);
	},

	refresh(frm) {
		set_queries(frm);
		_toggle_payments_grid(frm);
		_load_fee_info(frm);
		_setup_doc_previews_grid(frm);
		if (frm.doc.docstatus === 0) {
			render_turma_picker(frm);
			_populate_doc_previews(frm);
		}
		if (frm.doc.docstatus === 1 && frm.doc.student) {
			frm.add_custom_button(
				__("Ver Aluno"),
				() => frappe.set_route("Form", "Student", frm.doc.student)
			);
		}
	},

	first_name(frm) { update_full_name(frm); },
	last_name(frm)  { update_full_name(frm); },

	academic_year(frm) {
		frm.set_value("school_class", null);
		frm.set_value("class_group", null);
		set_queries(frm);
		clear_turma_picker(frm);
	},

	enrollment_type(frm) {
		_populate_doc_previews(frm, true);
		_apply_novo_class_filter(frm);
	},

	school_class(frm) {
		frm.set_value("class_group", null);
		set_queries(frm);
		render_turma_picker(frm);
	},

	class_group(frm) {
		highlight_selected_card(frm);
	},

	guardian(frm) {
		// When an existing guardian is selected, clear the inline fields
		if (frm.doc.guardian) {
			frm.set_value("guardian_first_name", null);
			frm.set_value("guardian_last_name", null);
			frm.set_value("guardian_relationship", null);
			frm.set_value("guardian_phone", null);
			frm.set_value("guardian_email", null);
		}
	},
});

// ---------------------------------------------------------------------------
// Child table events
// ---------------------------------------------------------------------------

frappe.ui.form.on("Renovacao Payment", {
	async mode_of_payment(frm, cdt, cdn) {
		if (frm.doctype !== "Inscricao" || frm.doc.docstatus !== 0) return;
		const fee = await frappe.db.get_single_value("School Settings", "enrollment_fee_amount");
		frappe.model.set_value(cdt, cdn, "amount", parseFloat(fee) || 0);
	},
});

// ---------------------------------------------------------------------------

function update_full_name(frm) {
	const parts = [frm.doc.first_name, frm.doc.last_name].filter(Boolean);
	frm.set_value("full_name", parts.join(" "));
}

function set_queries(frm) {
	frm.set_query("school_class", () => ({ filters: { is_active: 1 } }));
	frm.set_query("guardian", () => ({ filters: { is_active: 1 } }));

	const cg_filters = { is_active: 1 };
	if (frm.doc.academic_year) cg_filters.academic_year = frm.doc.academic_year;
	if (frm.doc.school_class) cg_filters.school_class = frm.doc.school_class;
	frm.set_query("class_group", () => ({ filters: cg_filters }));
}

function _toggle_payments_grid(frm) {
	const editable = frm.doc.docstatus === 0;
	const grid = frm.get_field("payments").grid;
	grid.toggle_add_delete_rows(editable);
	grid.editable_grid = true;

	if (frm.doc.__islocal && !(frm.doc.payments && frm.doc.payments.length)) {
		_prefill_payments_from_pos(frm);
	}
}

async function _prefill_payments_from_pos(frm) {
	const pos_profile = await frappe.db.get_single_value("School Settings", "enrollment_pos_profile");
	if (!pos_profile) return;

	const doc = await frappe.db.get_doc("POS Profile", pos_profile);
	if (!doc || !doc.payments || !doc.payments.length) return;

	const fee = parseFloat(await frappe.db.get_single_value("School Settings", "enrollment_fee_amount")) || 0;
	const count = doc.payments.length;

	(doc.payments || []).forEach((p, i) => {
		const row = frm.add_child("payments");
		row.mode_of_payment = p.mode_of_payment;
		row.amount = count === 1 ? fee : (i < count - 1 ? Math.floor(fee / count * 100) / 100 : 0);
	});
	frm.refresh_field("payments");
}

async function _load_fee_info(frm) {
	const wrapper = frm.fields_dict.fee_info_html?.$wrapper;
	if (!wrapper) return;
	const amount = await frappe.db.get_single_value("School Settings", "enrollment_fee_amount");
	if (amount && parseFloat(amount) > 0) {
		const fmt = frappe.format(parseFloat(amount), { fieldtype: "Currency" });
		wrapper.html(
			`<p style="color:var(--text-muted);font-size:13px;margin:0 0 8px;">
				${__("Valor da Taxa de Inscrição")}: <strong style="color:var(--text-color);">${fmt}</strong>
			</p>`
		);
	} else {
		wrapper.html("");
	}
}

// ---------------------------------------------------------------------------
// Docs preview (auto-populated child table)
// ---------------------------------------------------------------------------

function _setup_doc_previews_grid(frm) {
	const grid = frm.get_field("doc_previews")?.grid;
	if (!grid) return;
	grid.toggle_add_delete_rows(false);
	grid.editable_grid = true;
}

async function _populate_doc_previews(frm, force) {
	if (frm.doc.docstatus !== 0) return;

	const enrollment_type = frm.doc.enrollment_type;

	// On enrollment_type change, always repopulate (force=true).
	// On refresh, skip if rows already exist (secretary may have added files).
	const hasRows = frm.doc.doc_previews && frm.doc.doc_previews.length > 0;
	if (!force && hasRows) return;
	if (!enrollment_type) return;

	const r = await frappe.call({
		method: "escola.escola.doctype.inscricao.inscricao.get_required_docs_for_type",
		args: { enrollment_type },
	});

	const docs = r.message || [];

	// Preserve any files the secretary already attached before the type change
	const existing_files = {};
	(frm.doc.doc_previews || []).forEach(row => {
		if (row.document_type && row.file) existing_files[row.document_type] = row.file;
	});

	frm.clear_table("doc_previews");

	docs.forEach(d => {
		const row = frm.add_child("doc_previews");
		row.document_type = d.name;
		row.is_required = d.is_required;
		if (existing_files[d.name]) row.file = existing_files[d.name];
	});

	frm.refresh_field("doc_previews");
}

// ---------------------------------------------------------------------------
// Turma picker
// ---------------------------------------------------------------------------

function render_turma_picker(frm) {
	const wrapper = frm.fields_dict.turma_picker_html?.$wrapper;
	if (!wrapper) return;

	if (!frm.doc.academic_year || !frm.doc.school_class) {
		clear_turma_picker(frm);
		return;
	}

	frappe.call({
		method: "escola.escola.doctype.inscricao.inscricao.get_available_turmas",
		args: { academic_year: frm.doc.academic_year, school_class: frm.doc.school_class },
		callback(r) {
			if (r.exc) return;
			_render_cards(frm, r.message || []);
		},
	});
}

function _render_cards(frm, groups) {
	const wrapper = frm.fields_dict.turma_picker_html.$wrapper;

	if (!groups.length) {
		wrapper.html(
			`<p class="text-muted" style="padding:8px 0;">
				${__("Não existem turmas activas para esta Classe e Ano Lectivo.")}
			</p>`
		);
		return;
	}

	const cards_html = groups.map((g) => {
		const count = g.student_count || 0;
		const max = g.max_students || 0;
		const full = max > 0 && count >= max;
		const pct = max > 0 ? count / max : 0;
		const dot_color = full ? "var(--red)" : pct >= 0.9 ? "var(--yellow)" : "var(--green)";
		const capacity = max > 0 ? `${count} / ${max}` : `${count} ${__("aluno(s)")}`;
		const is_selected = frm.doc.class_group === g.name;

		return `
			<div class="turma-card${is_selected ? " selected" : ""}${full ? " full" : ""}"
				 data-name="${g.name}"
				 title="${full ? __("Turma sem vagas") : __("Clique para seleccionar")}">
				<div class="turma-card-name">${g.group_name}</div>
				${g.shift ? `<div class="turma-card-shift">${g.shift}</div>` : ""}
				<div class="turma-card-count" style="color:${dot_color};">
					${full ? "⛔ " : ""}${capacity}
				</div>
				${full ? `<div class="turma-card-badge">${__("Lotada")}</div>` : ""}
			</div>`;
	}).join("");

	wrapper.html(`
		<style>
			.turma-picker{display:flex;flex-wrap:wrap;gap:10px;margin:10px 0 4px;}
			.turma-card{border:2px solid var(--border-color);border-radius:8px;padding:12px 18px;min-width:110px;text-align:center;cursor:pointer;background:var(--card-bg);transition:border-color .15s,background .15s;user-select:none;}
			.turma-card:hover:not(.full){border-color:var(--primary);}
			.turma-card.selected{border-color:var(--primary);background:var(--primary-light);}
			.turma-card.full{opacity:.55;cursor:not-allowed;}
			.turma-card-name{font-weight:600;font-size:14px;}
			.turma-card-shift{font-size:11px;color:var(--text-muted);margin-top:2px;}
			.turma-card-count{font-size:13px;font-weight:500;margin-top:6px;}
			.turma-card-badge{display:inline-block;margin-top:4px;font-size:10px;background:var(--red-light);color:var(--red);padding:1px 6px;border-radius:4px;}
		</style>
		<div class="turma-picker">${cards_html}</div>
		<p style="margin:6px 0 0;font-size:12px;color:var(--text-muted);">
			<i class="fa fa-info-circle"></i>
			${__("Turma opcional — se não seleccionar, o aluno ficará como <b>Pendente de Turma</b> até ser alocado.")}
		</p>
	`);

	wrapper.find(".turma-card:not(.full)").on("click", function () {
		frm.set_value("class_group", $(this).data("name"));
	});
}

function highlight_selected_card(frm) {
	const wrapper = frm.fields_dict.turma_picker_html?.$wrapper;
	if (!wrapper) return;
	wrapper.find(".turma-card").each(function () {
		$(this).toggleClass("selected", $(this).data("name") === frm.doc.class_group);
	});
}

function clear_turma_picker(frm) {
	frm.fields_dict.turma_picker_html?.$wrapper.html("");
}

// ---------------------------------------------------------------------------
// Novo enrollment: restrict school_class to the entry level
// ---------------------------------------------------------------------------

async function _apply_novo_class_filter(frm) {
	if (frm.doc.enrollment_type !== "Novo") {
		frm.set_query("school_class", () => ({ filters: { is_active: 1 } }));
		return;
	}

	const rows = await frappe.db.get_list("School Class", {
		filters: { is_active: 1 },
		fields: ["name", "class_level"],
		order_by: "class_level asc",
		limit: 1,
	});

	if (!rows.length) return;

	const min_level = rows[0].class_level;

	frm.set_query("school_class", () => ({
		filters: { is_active: 1, class_level: min_level },
	}));

	if (!frm.doc.school_class) {
		frm.set_value("school_class", rows[0].name);
	}
}
