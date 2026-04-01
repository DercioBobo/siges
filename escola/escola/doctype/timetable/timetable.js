// Copyright (c) 2024, EntreTech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Timetable", {
	onload(frm) {
		_set_time_slot_filter(frm);
		frm.set_query("class_group", () => ({ filters: { is_active: 1 } }));
		frm.set_query("academic_term", () => ({ filters: { is_active: 1 } }));
	},

	refresh(frm) {
		_set_time_slot_filter(frm);

		if (!frm.is_new()) {
			frm.add_custom_button(__("Ver Horário"), () => {
				frappe.set_route("timetable-view");
			}, __("Acções"));

			if (frm.doc.status === "Rascunho") {
				frm.add_custom_button(__("Activar"), () => {
					frappe.confirm(
						__("Activar este horário? O horário anterior desta turma/período será arquivado."),
						() => {
							frm.set_value("status", "Activo");
							frm.save();
						}
					);
				}, __("Acções"));
			}
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
