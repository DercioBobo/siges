// Copyright (c) 2024, EntreTech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Timetable", {
	onload(frm) {
		_set_time_slot_filter(frm);
		frm.set_query("class_group", () => ({ filters: { is_active: 1 } }));
	},

	refresh(frm) {
		_set_time_slot_filter(frm);
		const grid = frm.fields_dict.timetable_entries.grid;
		grid.toggle_enable("day_of_week", true);
		grid.df.in_editable_grid = 1;
		// Open the grid dialog when clicking any row instead of the Frappe row modal
		grid.wrapper.off("click.opengrid").on("click.opengrid", ".data-row", function (e) {
			if ($(e.target).closest("button, input[type=checkbox]").length) return;
			_open_grid_dialog(frm);
		});

		// Prefill academic_year on new docs from School Settings
		if (frm.is_new() && !frm.doc.academic_year) {
			frappe.db.get_single_value("School Settings", "current_academic_year").then(val => {
				if (val) frm.set_value("academic_year", val);
			});
		}

		// Primary action button
		frm.page.set_primary_action(__("Preencher em Grade"), () => {
			_open_grid_dialog(frm);
		}, "edit");

		if (!frm.is_new()) {
			frm.add_custom_button(__("Ver Horário"), () => {
				frappe.set_route("timetable-view");
			}, __("Acções"));
		}
	},

	class_group(frm) {
		if (frm.doc.class_group) {
			frappe.db.get_value("Class Group", frm.doc.class_group, "shift", r => {
				if (r && r.shift) {
					frm.set_value("shift", r.shift);
					_set_time_slot_filter(frm);
					frm.refresh_field("timetable_entries");
				}
			});
			// Auto-open grid on new docs once class_group (and thus shift) is set
			if (frm.is_new()) {
				setTimeout(() => _open_grid_dialog(frm), 400);
			}
		}
	},
});

frappe.ui.form.on("Timetable Entry", {
	subject(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.subject || !frm.doc.class_group) return;

		frappe.call({
			method: "escola.escola.doctype.timetable.timetable.get_curriculum_teacher",
			args: { class_group: frm.doc.class_group, subject: row.subject },
			callback(r) {
				if (r.message) {
					frappe.model.set_value(cdt, cdn, "teacher", r.message);
				}
			},
		});
	},
});

async function _open_grid_dialog(frm) {
	const DAYS = ["Segunda-Feira", "Terça-Feira", "Quarta-Feira", "Quinta-Feira", "Sexta-Feira"];
	const DAY_SHORT = ["Seg", "Ter", "Qua", "Qui", "Sex"];

	// 1. Load time slots for the current shift
	const slotFilters = { is_active: 1 };
	if (frm.doc.shift) slotFilters.shift = frm.doc.shift;
	const slots = await frappe.db.get_list("Time Slot", {
		filters: slotFilters,
		fields: ["name", "label", "slot_type"],
		order_by: "name asc",
		limit: 100,
	});

	if (!slots.length) {
		frappe.msgprint(__("Nenhum Horário (Time Slot) encontrado para este turno."));
		return;
	}

	// 2. Load subjects from active curriculum, fallback to all subjects
	let subjects = [];
	if (frm.doc.class_group) {
		const curricula = await frappe.db.get_list("Class Curriculum", {
			filters: { class_group: frm.doc.class_group, is_active: 1 },
			fields: ["name"],
			limit: 1,
		});
		if (curricula.length) {
			const currDoc = await frappe.db.get_doc("Class Curriculum", curricula[0].name);
			subjects = (currDoc.subject_lines || []).map(l => l.subject).filter(Boolean);
		}
	}
	if (!subjects.length) {
		const all = await frappe.db.get_list("Subject", {
			filters: { is_active: 1 },
			fields: ["name"],
			limit: 200,
		});
		subjects = all.map(s => s.name);
	}

	// 3. Pre-populate from existing entries
	const existing = {};
	(frm.doc.timetable_entries || []).forEach(e => {
		existing[`${e.day_of_week}||${e.time_slot}`] = e.subject || "";
	});

	// 4. Build grid HTML
	const opts = ['<option value=""></option>',
		...subjects.map(s => `<option value="${frappe.utils.escape_html(s)}">${frappe.utils.escape_html(s)}</option>`)
	].join("");

	let rows = "";
	slots.forEach(slot => {
		const label = slot.label || slot.name;
		const isBreak = slot.slot_type && slot.slot_type !== "Aula";
		const rowStyle = isBreak ? "background:#f8f9fa;" : "";

		rows += `<tr style="${rowStyle}">
			<td style="white-space:nowrap;font-weight:500;padding:4px 8px;min-width:90px">
				${frappe.utils.escape_html(label)}
			</td>`;

		DAYS.forEach(day => {
			if (isBreak) {
				rows += `<td style="text-align:center;color:#aaa;padding:4px">—</td>`;
			} else {
				const key = `${day}||${slot.name}`;
				rows += `<td style="padding:2px">
					<select class="form-control form-control-sm tg-cell"
						data-day="${frappe.utils.escape_html(day)}"
						data-slot="${frappe.utils.escape_html(slot.name)}"
						style="font-size:11px;padding:2px 4px;height:28px">${opts}</select>
				</td>`;
			}
		});
		rows += `</tr>`;
	});

	const html = `
		<div style="overflow-x:auto">
		<table class="table table-bordered table-condensed" style="font-size:12px;margin-bottom:0">
			<thead>
				<tr style="background:#f0f0f0">
					<th style="padding:6px 8px">Horário</th>
					${DAY_SHORT.map(d => `<th style="text-align:center;padding:6px 8px;min-width:110px">${d}</th>`).join("")}
				</tr>
			</thead>
			<tbody>${rows}</tbody>
		</table>
		</div>`;

	const d = new frappe.ui.Dialog({
		title: __("Preencher Horário em Grade"),
		fields: [{ fieldtype: "HTML", fieldname: "grid_html", options: html }],
		size: "extra-large",
		primary_action_label: __("Aplicar"),
		async primary_action() {
			// Collect filled cells
			const entries = [];
			d.$wrapper.find(".tg-cell").each(function () {
				const subject = $(this).val();
				if (!subject) return;
				entries.push({
					day_of_week: $(this).data("day"),
					time_slot: $(this).data("slot"),
					subject,
				});
			});

			// Replace child table
			frm.clear_table("timetable_entries");
			for (const e of entries) {
				const row = frm.add_child("timetable_entries");
				row.day_of_week = e.day_of_week;
				row.time_slot = e.time_slot;
				row.subject = e.subject;
			}
			frm.refresh_field("timetable_entries");
			d.hide();

			// Auto-fill teachers from curriculum (batch)
			if (frm.doc.class_group) {
				const filling = frm.doc.timetable_entries.map(row =>
					frappe.call({
						method: "escola.escola.doctype.timetable.timetable.get_curriculum_teacher",
						args: { class_group: frm.doc.class_group, subject: row.subject },
					}).then(r => {
						if (r.message) {
							frappe.model.set_value(row.doctype, row.name, "teacher", r.message);
						}
					})
				);
				await Promise.all(filling);
				frm.refresh_field("timetable_entries");
			}
		},
	});

	d.show();

	// Set pre-existing values after DOM renders
	setTimeout(() => {
		d.$wrapper.find(".tg-cell").each(function () {
			const key = `${$(this).data("day")}||${$(this).data("slot")}`;
			if (existing[key]) $(this).val(existing[key]);
		});
	}, 150);
}

function _set_time_slot_filter(frm) {
	const shift = frm.doc.shift;
	frm.set_query("time_slot", "timetable_entries", () => ({
		filters: Object.assign(
			{ is_active: 1 },
			shift ? { shift } : {}
		),
	}));
	frm.set_query("teacher", "timetable_entries", () => ({
		filters: { is_active: 1 },
	}));
	frm.set_query("subject", "timetable_entries", () => ({
		filters: { is_active: 1 },
	}));
}
