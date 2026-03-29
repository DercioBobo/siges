frappe.ui.form.on("Class Curriculum", {
    refresh(frm) {
        frm.set_query("school_class", () => ({ filters: { is_active: 1 } }));

        if (!frm.doc.__islocal) {
            _show_summary(frm);
        }

        // Button: bulk-assign homeroom teacher to all non-specialist subjects
        frm.add_custom_button(__("Preencher Professor Titular"), () => {
            _fill_homeroom_teacher(frm);
        });
    },

    school_class(frm) {
        // Cache the homeroom teacher whenever the class changes
        _load_homeroom_teacher(frm);
    },

    subject_lines_add(frm) { _show_summary(frm); },
    subject_lines_remove(frm) { _show_summary(frm); },
});

frappe.ui.form.on("Class Curriculum Line", {
    subject(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        if (!row.subject) return;

        frappe.db.get_value("Subject", row.subject, ["is_specialist", "default_teacher"], (r) => {
            if (!r) return;

            if (r.is_specialist) {
                // Specialist subject: use the subject's own default_teacher (if any)
                if (r.default_teacher) {
                    frappe.model.set_value(cdt, cdn, "teacher", r.default_teacher);
                }
                // else leave blank — user must fill manually
            } else {
                // Regular subject: auto-fill from class homeroom teacher
                const homeroom = frm._homeroom_teacher;
                if (homeroom) {
                    frappe.model.set_value(cdt, cdn, "teacher", homeroom);
                }
            }
        });
    },
});

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function _load_homeroom_teacher(frm) {
    if (!frm.doc.school_class) {
        frm._homeroom_teacher = null;
        return;
    }
    frappe.db.get_value("School Class", frm.doc.school_class, "default_teacher", (r) => {
        frm._homeroom_teacher = r ? r.default_teacher : null;
    });
}

function _fill_homeroom_teacher(frm) {
    if (!frm.doc.school_class) {
        frappe.msgprint(__("Seleccione a Classe primeiro."));
        return;
    }

    frappe.db.get_value("School Class", frm.doc.school_class, "default_teacher", (r) => {
        const homeroom = r ? r.default_teacher : null;
        if (!homeroom) {
            frappe.msgprint({
                message: __("A Classe <b>{0}</b> não tem Professor Titular definido. "
                          + "Configure o Professor Titular na ficha da Classe.", [frm.doc.school_class]),
                title: __("Professor Titular em falta"),
                indicator: "orange",
            });
            return;
        }

        // Collect subjects that need checking (non-specialist lines without a teacher)
        const lines = frm.doc.subject_lines || [];
        if (!lines.length) return;

        // Fetch is_specialist for all subjects in the table in one call
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

function _show_summary(frm) {
    const lines = frm.doc.subject_lines || [];
    const total = lines.length;
    if (!total) return;

    const withTeacher = lines.filter(l => l.teacher).length;
    const withoutTeacher = total - withTeacher;

    let msg = __("{0} disciplina(s)", [total]);
    if (withoutTeacher > 0) {
        msg += ` &nbsp;|&nbsp; <span style="color:var(--orange-600)">${__("{0} sem professor atribuído", [withoutTeacher])}</span>`;
    }
    frm.dashboard.set_headline(msg);
}
