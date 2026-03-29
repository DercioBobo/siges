frappe.ui.form.on("Grade Entry", {
    refresh(frm) {
        _set_queries(frm);

        frm.add_custom_button(__("Carregar Alunos"), () => {
            _load_grade_rows(frm);
        });
    },

    class_group(frm) {
        _set_queries(frm);
    },

    academic_year(frm) {
        frm.set_value("academic_term", null);
        _set_queries(frm);
    },

    school_class(frm) {
        frm.set_value("class_group", null);
        _set_queries(frm);
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
        _recalc_approved(frm, cdt, cdn);
    },
});

// ---------------------------------------------------------------------------
// Helpers
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

    if (frm.doc.class_group) {
        frm.set_query("subject", () => ({
            query: "frappe.client.get_list",
            filters: {},
        }));
    }
}

function _recalc_approved(frm, cdt, cdn) {
    const row = frappe.get_doc(cdt, cdn);
    const min_pass = _get_min_pass(frm);
    if (row.is_absent || row.score === null || row.score === undefined || row.score === "") {
        frappe.model.set_value(cdt, cdn, "is_approved", 0);
    } else {
        frappe.model.set_value(cdt, cdn, "is_approved", parseFloat(row.score) >= min_pass ? 1 : 0);
    }
}

function _get_min_pass(frm) {
    // Default 10; ideally fetched from School Class but keep it simple client-side
    return 10;
}

async function _load_grade_rows(frm) {
    if (!frm.doc.class_group || !frm.doc.academic_year) {
        frappe.msgprint(__("Seleccione a Turma e o Ano Lectivo antes de carregar os alunos."));
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
    } else {
        frappe.show_alert({
            message: __("Todos os alunos já constam da pauta."),
            indicator: "blue",
        });
    }
}
