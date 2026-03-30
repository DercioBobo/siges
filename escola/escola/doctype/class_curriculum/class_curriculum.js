frappe.ui.form.on("Class Curriculum", {
    onload(frm) {
        escola.utils.auto_fill_academic_year(frm);
    },

    refresh(frm) {
        _set_cg_query(frm);

        if (!frm.doc.__islocal) {
            _show_summary(frm);
        }

        frm.add_custom_button(__("Preencher Professor Titular"), () => {
            _fill_homeroom_teacher(frm);
        });
    },

    school_class(frm) {
        frm.set_value("class_group", null);
        _set_cg_query(frm);
    },

    class_group(frm) {
        _set_cg_query(frm);
        if (!frm.doc.class_group) return;
        _populate_from_class_group(frm);
    },

    subject_lines_add(frm) { _show_summary(frm); },
    subject_lines_remove(frm) { _show_summary(frm); },
});

// ---------------------------------------------------------------------------
// Queries
// ---------------------------------------------------------------------------

function _set_cg_query(frm) {
    const f = { is_active: 1 };
    if (frm.doc.school_class) f.school_class = frm.doc.school_class;
    if (frm.doc.academic_year) f.academic_year = frm.doc.academic_year;
    frm.set_query("class_group", () => ({ filters: f }));
    frm.set_query("school_class", () => ({ filters: { is_active: 1 } }));
}

// ---------------------------------------------------------------------------
// Auto-populate on class_group selection
// ---------------------------------------------------------------------------

function _populate_from_class_group(frm) {
    frappe.call({
        method: "escola.escola.doctype.class_curriculum.class_curriculum.get_class_group_curriculum_data",
        args: { class_group: frm.doc.class_group },
        callback(r) {
            if (r.exc) return;
            const data = r.message;

            if (data.error === "class_group_not_found") return;

            if (data.error === "no_subjects") {
                frappe.msgprint({
                    message: __("A Classe <b>{0}</b> não tem disciplinas definidas. "
                              + "Adicione as disciplinas na ficha da Classe antes de criar a Grelha Curricular.",
                              [data.school_class]),
                    title: __("Disciplinas em falta"),
                    indicator: "orange",
                });
                return;
            }

            if (!data.class_teacher) {
                frappe.msgprint({
                    message: __("A Turma <b>{0}</b> não tem Professor Titular definido. "
                              + "Defina o Professor Titular na ficha da Turma para que as disciplinas "
                              + "sejam preenchidas automaticamente.",
                              [frm.doc.class_group]),
                    title: __("Professor Titular em falta"),
                    indicator: "orange",
                });
            }

            // Clear existing lines and repopulate
            frm.clear_table("subject_lines");
            data.subjects.forEach(s => {
                const row = frm.add_child("subject_lines");
                row.subject = s.subject;
                row.teacher = (!s.is_specialist && data.class_teacher) ? data.class_teacher : null;
            });

            frm.refresh_field("subject_lines");
            _show_summary(frm);
        },
    });
}

// ---------------------------------------------------------------------------
// Preencher Professor Titular (re-apply homeroom teacher to non-specialist lines)
// ---------------------------------------------------------------------------

function _fill_homeroom_teacher(frm) {
    if (!frm.doc.class_group) {
        frappe.msgprint(__("Seleccione a Turma primeiro."));
        return;
    }

    frappe.db.get_value("Class Group", frm.doc.class_group, "class_teacher", (r) => {
        const homeroom = r ? r.class_teacher : null;
        if (!homeroom) {
            frappe.msgprint({
                message: __("A Turma <b>{0}</b> não tem Professor Titular definido.", [frm.doc.class_group]),
                title: __("Professor Titular em falta"),
                indicator: "orange",
            });
            return;
        }

        const lines = frm.doc.subject_lines || [];
        if (!lines.length) return;

        const subjects = [...new Set(lines.map(l => l.subject).filter(Boolean))];
        frappe.call({
            method: "frappe.client.get_list",
            args: {
                doctype: "Subject",
                filters: [["name", "in", subjects]],
                fields: ["name", "is_specialist"],
                limit_page_length: subjects.length,
            },
            callback(res) {
                const specialistSet = new Set(
                    (res.message || []).filter(s => s.is_specialist).map(s => s.name)
                );
                let filled = 0;
                lines.forEach(row => {
                    if (row.subject && !specialistSet.has(row.subject)) {
                        frappe.model.set_value(row.doctype, row.name, "teacher", homeroom);
                        filled++;
                    }
                });
                frm.refresh_field("subject_lines");
                frappe.show_alert({
                    message: __("Professor titular aplicado a {0} disciplina(s).", [filled]),
                    indicator: "green",
                });
                _show_summary(frm);
            },
        });
    });
}

// ---------------------------------------------------------------------------
// Summary headline
// ---------------------------------------------------------------------------

function _show_summary(frm) {
    const lines = frm.doc.subject_lines || [];
    if (!lines.length) return;

    const withoutTeacher = lines.filter(l => !l.teacher).length;
    let msg = __("{0} disciplina(s)", [lines.length]);
    if (withoutTeacher > 0) {
        msg += ` &nbsp;|&nbsp; <span style="color:var(--orange-600)">${__("{0} sem professor atribuído", [withoutTeacher])}</span>`;
    }
    frm.dashboard.set_headline(msg);
}
