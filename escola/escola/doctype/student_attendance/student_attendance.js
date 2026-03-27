// Copyright (c) 2024, EntreTech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Student Attendance", {
	refresh(frm) {
		set_class_group_query(frm);

		frm.add_custom_button(__("Carregar Alunos"), () => {
			load_students(frm);
		});
	},

	academic_year(frm) {
		frm.set_value("class_group", null);
		set_class_group_query(frm);
	},

	school_class(frm) {
		frm.set_value("class_group", null);
		set_class_group_query(frm);
	},

	class_group(frm) {
		if (!frm.doc.class_group) return;

		frappe.db
			.get_value("Class Group", frm.doc.class_group, "class_teacher")
			.then((r) => {
				if (r.message && r.message.class_teacher) {
					frm.set_value("teacher", r.message.class_teacher);
				}
			});
	},
});

function set_class_group_query(frm) {
	const filters = { is_active: 1 };
	if (frm.doc.academic_year) filters.academic_year = frm.doc.academic_year;
	if (frm.doc.school_class) filters.school_class = frm.doc.school_class;

	frm.set_query("class_group", () => ({ filters }));
}

async function load_students(frm) {
	if (!frm.doc.class_group || !frm.doc.academic_year) {
		frappe.msgprint(
			__("Por favor, seleccione a Turma e o Ano Lectivo antes de carregar os alunos.")
		);
		return;
	}

	const r = await frappe.call({
		method:
			"escola.escola.doctype.student_attendance.student_attendance.get_students_for_attendance",
		args: {
			class_group: frm.doc.class_group,
			academic_year: frm.doc.academic_year,
		},
	});

	if (!r.message || !r.message.length) {
		frappe.msgprint(
			__("Não foram encontrados alunos activos para esta turma no ano lectivo seleccionado.")
		);
		return;
	}

	const existing_students = new Set(
		(frm.doc.attendance_entries || []).map((e) => e.student)
	);

	let added = 0;
	for (const s of r.message) {
		if (!existing_students.has(s.student)) {
			const row = frappe.model.add_child(
				frm.doc,
				"Student Attendance Entry",
				"attendance_entries"
			);
			row.student = s.student;
			row.attendance_status = "Presente";
			added++;
		}
	}

	frm.refresh_field("attendance_entries");

	if (added > 0) {
		frappe.show_alert({
			message: __("{0} aluno(s) carregado(s) com sucesso.", [added]),
			indicator: "green",
		});
	} else {
		frappe.show_alert({
			message: __("Todos os alunos já constam da lista de presença."),
			indicator: "blue",
		});
	}
}
