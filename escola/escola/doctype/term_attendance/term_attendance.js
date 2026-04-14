frappe.ui.form.on("Term Attendance", {
    onload(frm) {
        escola.utils.auto_fill_academic_year(frm);
    },

    refresh(frm) {
        _set_queries(frm);

        const grid = frm.fields_dict["attendance_rows"] && frm.fields_dict["attendance_rows"].grid;
        if (grid) {
            grid.cannot_add_rows = true;
            grid.cannot_delete_rows = true;
        }

        frm.add_custom_button(__("Carregar Alunos"), () => _load_students(frm));

        if (!frm.doc.__islocal) {
            frm.add_custom_button(__("Sincronizar Alunos"), () => _sync_attendance_students(frm));
            _show_summary(frm);
        }
    },

    school_class(frm) {
        frm.set_value("class_group", null);
        _set_queries(frm);
    },

    async class_group(frm) {
        _set_queries(frm);
        if (!frm.doc.class_group) return;

        const cg = await frappe.db.get_value(
            "Class Group", frm.doc.class_group, ["academic_year"]
        );
        const academic_year = (cg && cg.academic_year) || frm.doc.academic_year;
        if (academic_year && frm.doc.academic_year !== academic_year) {
            frm.set_value("academic_year", academic_year);
        }

        if (academic_year && !frm.doc.academic_term) {
            await _auto_fill_term(frm, academic_year);
        }

        if (frm.doc.__islocal && frm.doc.academic_term) {
            _load_students(frm);
        }
    },

    async academic_year(frm) {
        frm.set_value("academic_term", null);
        if (frm.doc.academic_year) {
            await _auto_fill_term(frm, frm.doc.academic_year);
        }
    },

    academic_term(frm) {
        if (frm.doc.__islocal && frm.doc.class_group && frm.doc.academic_year
                && !(frm.doc.attendance_rows && frm.doc.attendance_rows.length)) {
            _load_students(frm);
        }
    },
});

frappe.ui.form.on("Term Attendance Row", {
    justified_absences(frm, cdt, cdn) { _recalc_row(frm, cdt, cdn); },
    unjustified_absences(frm, cdt, cdn) { _recalc_row(frm, cdt, cdn); },
});

// ---------------------------------------------------------------------------
// Sync students
// ---------------------------------------------------------------------------

function _sync_attendance_students(frm) {
    frappe.confirm(
        __("Alunos sem estado 'Activo' serão removidos. As faltas dos restantes são preservadas. Continuar?"),
        () => {
            frappe.call({
                method: "escola.escola.doctype.term_attendance.term_attendance.sync_term_attendance_students",
                args: { doc_name: frm.doc.name },
                freeze: true,
                freeze_message: __("A sincronizar alunos…"),
                callback(r) {
                    if (!r.message) return;
                    const { removed, kept } = r.message;
                    if (removed > 0) {
                        frappe.show_alert({
                            message: __("{0} aluno(s) removido(s), {1} mantido(s).", [removed, kept]),
                            indicator: "orange",
                        });
                        frm.reload_doc();
                    } else {
                        frappe.show_alert({
                            message: __("Todos os alunos estão activos. Nenhuma alteração."),
                            indicator: "green",
                        });
                    }
                },
            });
        }
    );
}

// ---------------------------------------------------------------------------

function _set_queries(frm) {
    const cg_filters = { is_active: 1 };
    if (frm.doc.school_class) cg_filters.school_class = frm.doc.school_class;
    if (frm.doc.academic_year) cg_filters.academic_year = frm.doc.academic_year;
    frm.set_query("class_group", () => ({ filters: cg_filters }));
    frm.set_query("school_class", () => ({ filters: { is_active: 1 } }));
    frm.set_query("academic_term", () => {
        const f = { is_active: 1 };
        if (frm.doc.academic_year) f.academic_year = frm.doc.academic_year;
        return { filters: f };
    });
}

async function _auto_fill_term(frm, academic_year) {
    // Reuse the same server helper as Grade Entry
    const r = await frappe.call({
        method: "escola.escola.doctype.grade_entry.grade_entry.get_current_academic_term",
        args: { academic_year },
    });
    if (r.message && !frm.doc.academic_term) {
        frm.set_value("academic_term", r.message);
    }
}

async function _load_students(frm) {
    if (!frm.doc.class_group || !frm.doc.academic_year) {
        frappe.msgprint(__("Seleccione a Turma primeiro."));
        return;
    }
    if (!frm.doc.academic_term) {
        frappe.msgprint(__("Não foi possível detectar o Período. Seleccione manualmente."));
        return;
    }

    const r = await frappe.call({
        method: "escola.escola.doctype.term_attendance.term_attendance.get_attendance_students",
        args: {
            class_group: frm.doc.class_group,
            academic_year: frm.doc.academic_year,
        },
    });

    if (!r.message || !r.message.length) {
        frappe.msgprint(
            __("Não foram encontrados alunos activos para a Turma <b>{0}</b>.", [frm.doc.class_group])
        );
        return;
    }

    // Clear any auto-inserted empty rows before loading real data
    if ((frm.doc.attendance_rows || []).every(r => !r.student)) {
        frm.clear_table("attendance_rows");
    }

    const existing = new Set((frm.doc.attendance_rows || []).map(r => r.student));
    let added = 0;
    for (const s of r.message) {
        if (!existing.has(s.student)) {
            const row = frappe.model.add_child(frm.doc, "Term Attendance Row", "attendance_rows");
            row.student = s.student;
            row.justified_absences = 0;
            row.unjustified_absences = 0;
            added++;
        }
    }

    frm.refresh_field("attendance_rows");
    if (added > 0) {
        frappe.show_alert({ message: __("{0} aluno(s) adicionado(s).", [added]), indicator: "green" });
    } else {
        frappe.show_alert({ message: __("Todos os alunos já constam da lista."), indicator: "blue" });
    }
}

function _recalc_row(frm, cdt, cdn) {
    const row = frappe.get_doc(cdt, cdn);
    const total = (row.justified_absences || 0) + (row.unjustified_absences || 0);
    frappe.model.set_value(cdt, cdn, "total_absences", total);

    // Client-side at_risk preview (server recalculates on save with correct threshold)
    const threshold = frappe.sys_defaults && frappe.sys_defaults.max_absences_threshold
        ? parseInt(frappe.sys_defaults.max_absences_threshold)
        : 0;
    frappe.model.set_value(cdt, cdn, "at_risk", threshold > 0 && total >= threshold ? 1 : 0);

    _show_summary(frm);
}

function _show_summary(frm) {
    const rows = frm.doc.attendance_rows || [];
    const atRisk = rows.filter(r => r.at_risk).length;
    if (!rows.length) return;
    let msg = __("{0} aluno(s)", [rows.length]);
    if (atRisk > 0) {
        msg += ` &nbsp;|&nbsp; <span style="color:var(--orange-600)">${__("{0} em risco de faltas", [atRisk])}</span>`;
    }
    frm.dashboard.set_headline(msg);
}
