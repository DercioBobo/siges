// Copyright (c) 2024, EntreTech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Inscricao", {
	refresh(frm) {
		set_queries(frm);
		if (frm.doc.docstatus === 0) {
			render_turma_picker(frm);
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
