frappe.ui.form.on("Grade Entry", {
    onload(frm) {
        escola.utils.auto_fill_academic_year(frm);
    },

    refresh(frm) {
        _set_queries(frm);

        frm.add_custom_button(__("Carregar Alunos"), () => {
            _load_grade_rows(frm);
        });
    },

    async class_group(frm) {
        _set_queries(frm);
        if (!frm.doc.class_group) return;

        // academic_year comes from fetch_from but may not be ready yet — read it directly
        const cg = await frappe.db.get_value(
            "Class Group", frm.doc.class_group, ["academic_year"]
        );
        const academic_year = (cg && cg.academic_year) || frm.doc.academic_year;
        if (academic_year && frm.doc.academic_year !== academic_year) {
            frm.set_value("academic_year", academic_year);
        }

        // Auto-detect the current academic term from today's date
        if (academic_year && !frm.doc.academic_term) {
            await _auto_fill_term(frm, academic_year);
        }

        // Auto-load rows on new docs once turma + term are known
        if (frm.doc.__islocal && frm.doc.academic_term) {
            _load_grade_rows(frm);
        }
    },

    async academic_year(frm) {
        frm.set_value("academic_term", null);
        _set_queries(frm);
        if (frm.doc.academic_year) {
            await _auto_fill_term(frm, frm.doc.academic_year);
        }
    },

    academic_term(frm) {
        _set_queries(frm);
        // If class_group already selected and rows are empty, auto-load
        if (frm.doc.__islocal && frm.doc.class_group && frm.doc.academic_year
                && !(frm.doc.grade_rows && frm.doc.grade_rows.length)) {
            _load_grade_rows(frm);
        }
    },

    school_class(frm) {
        frm.set_value("class_group", null);
        _set_queries(frm);
    },

    subject(frm) {
        // Subject filter changed — reload rows if already have class_group + term
        if (frm.doc.__islocal && frm.doc.class_group && frm.doc.academic_term) {
            frappe.confirm(
                __("Recarregar alunos com a nova configuração de disciplina?"),
                () => {
                    frm.clear_table("grade_rows");
                    frm.refresh_field("grade_rows");
                    _load_grade_rows(frm);
                }
            );
        }
    },
});

frappe.ui.form.on("Grade Entry Row", {
    is_absent(frm, cdt, cdn) {
        const row = frappe.get_doc(cdt, cdn);
        if (row.is_absent) {
            frappe.model.set_value(cdt, cdn, "score", null);
            frappe.model.set_value(cdt, cdn, "is_approved", 0);
        }
    },

    score(frm, cdt, cdn) {
        const row = frappe.get_doc(cdt, cdn);
        if (row.is_absent) return;
        const min_pass = 10; // server recalculates on save; this is a client preview
        const s = parseFloat(row.score);
        frappe.model.set_value(
            cdt, cdn, "is_approved",
            (!isNaN(s) ? (s >= min_pass ? 1 : 0) : 0)
        );
    },
});

// ---------------------------------------------------------------------------
// Auto-fill helpers
// ---------------------------------------------------------------------------

async function _auto_fill_term(frm, academic_year) {
    const r = await frappe.call({
        method: "escola.escola.doctype.grade_entry.grade_entry.get_current_academic_term",
        args: { academic_year },
    });
    if (r.message && !frm.doc.academic_term) {
        frm.set_value("academic_term", r.message);
    }
}

// ---------------------------------------------------------------------------
// Queries
// ---------------------------------------------------------------------------

function _set_queries(frm) {
    frm.set_query("academic_term", () => {
        const f = { is_active: 1 };
        if (frm.doc.academic_year) f.academic_year = frm.doc.academic_year;
        return { filters: f };
    });

    frm.set_query("class_group", () => {
        const f = { is_active: 1 };
        if (frm.doc.academic_year) f.academic_year = frm.doc.academic_year;
        if (frm.doc.school_class) f.school_class = frm.doc.school_class;
        return { filters: f };
    });

    frm.set_query("school_class", () => ({ filters: { is_active: 1 } }));
}

// ---------------------------------------------------------------------------
// Load rows
// ---------------------------------------------------------------------------

async function _load_grade_rows(frm) {
    if (!frm.doc.class_group || !frm.doc.academic_year) {
        frappe.msgprint(__("Seleccione a Turma primeiro."));
        return;
    }
    if (!frm.doc.academic_term) {
        frappe.msgprint(__("Não foi possível detectar o Período Académico actual. Seleccione o Período manualmente."));
        return;
    }

    const r = await frappe.call({
        method: "escola.escola.doctype.grade_entry.grade_entry.get_grade_entry_students",
        args: {
            class_group: frm.doc.class_group,
            academic_year: frm.doc.academic_year,
            subject: frm.doc.subject || null,
        },
    });

    if (!r.message) return;

    if (r.message.error === "no_students") {
        frappe.msgprint(
            __("Não foram encontrados alunos activos para a Turma <b>{0}</b>. "
                + "Verifique as Alocações de Turma.", [frm.doc.class_group])
        );
        return;
    }
    if (r.message.error === "no_subjects") {
        frappe.msgprint(
            __("Não existe Grelha Curricular activa para a Turma <b>{0}</b>. "
                + "Crie a Grelha Curricular antes de lançar notas.", [frm.doc.class_group])
        );
        return;
    }

    const existing = new Set(
        (frm.doc.grade_rows || []).map(r => r.student + "||" + r.subject)
    );

    let added = 0;
    for (const combo of r.message) {
        const key = combo.student + "||" + combo.subject;
        if (!existing.has(key)) {
            const row = frappe.model.add_child(frm.doc, "Grade Entry Row", "grade_rows");
            row.student = combo.student;
            row.subject = combo.subject;
            added++;
        }
    }

    frm.refresh_field("grade_rows");

    if (added > 0) {
        frappe.show_alert({
            message: __("{0} linha(s) adicionada(s) à pauta.", [added]),
            indicator: "green",
        });
    } else if (!existing.size) {
        frappe.show_alert({ message: __("Nenhuma linha encontrada."), indicator: "orange" });
    } else {
        frappe.show_alert({
            message: __("Todos os alunos já constam da pauta."),
            indicator: "blue",
        });
    }
}
