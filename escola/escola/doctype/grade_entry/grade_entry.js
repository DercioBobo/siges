frappe.ui.form.on("Grade Entry", {
    onload(frm) {
        escola.utils.auto_fill_academic_year(frm);
    },

    refresh(frm) {
        _set_queries(frm);
        _setup_grid(frm);

        frm.add_custom_button(__("Carregar Alunos"), () => _load_grade_rows(frm));

        if (!frm.doc.__islocal) {
            frm.add_custom_button(__("Sincronizar Alunos"), () => _sync_students(frm));

            if (frm.doc.class_group && frm.doc.academic_term) {
                frm.add_custom_button(
                    __("Mapa de Aproveitamento"),
                    () => {
                        frappe.route_options = {
                            class_group:   frm.doc.class_group,
                            academic_term: frm.doc.academic_term,
                        };
                        frappe.set_route("mapa-aproveitamento");
                    },
                    __("Ver")
                );
            }
        }
    },

    async class_group(frm) {
        _set_queries(frm);
        if (!frm.doc.class_group) return;

        const cg = await frappe.db.get_value("Class Group", frm.doc.class_group, ["academic_year"]);
        const academic_year = (cg && cg.academic_year) || frm.doc.academic_year;

        if (academic_year && frm.doc.academic_year !== academic_year) {
            frm.set_value("academic_year", academic_year);
        }
        if (academic_year && !frm.doc.academic_term) {
            await _auto_fill_term(frm, academic_year);
        }
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
        if (frm.doc.__islocal && frm.doc.class_group && frm.doc.academic_year
                && !(frm.doc.grade_rows && frm.doc.grade_rows.length)) {
            _load_grade_rows(frm);
        }
    },

    school_class(frm) {
        frm.set_value("class_group", null);
        _set_queries(frm);
    },
});

// ---------------------------------------------------------------------------
// Grade Entry Row — real-time MACS / MT calculation
// ---------------------------------------------------------------------------

frappe.ui.form.on("Grade Entry Row", {
    acsp_1(frm, cdt, cdn) { _recalc(frm, cdt, cdn); },
    acsp_2(frm, cdt, cdn) { _recalc(frm, cdt, cdn); },
    acse_1(frm, cdt, cdn) { _recalc(frm, cdt, cdn); },
    acse_2(frm, cdt, cdn) { _recalc(frm, cdt, cdn); },
    acp(frm, cdt, cdn)    { _recalc(frm, cdt, cdn); },

    is_absent(frm, cdt, cdn) {
        const row = frappe.get_doc(cdt, cdn);
        if (!row.is_absent) return;
        const clear_fields = ["acsp_1","acsp_2","acse_1","acse_2","acp","macsp","macs","mt"];
        clear_fields.forEach(f => frappe.model.set_value(cdt, cdn, f, null));
    },
});

// Helpers ---------------------------------------------------------------

function _num(v) {
    return (v !== null && v !== undefined && v !== "") ? parseFloat(v) : null;
}

function _round2(v) {
    return Math.round(v);
}

function _recalc(frm, cdt, cdn) {
    const row = frappe.get_doc(cdt, cdn);
    if (row.is_absent) return;

    // MACSP = mean of non-null ACSP values
    const acsp_vals = [row.acsp_1, row.acsp_2].map(_num).filter(v => v !== null);
    const macsp = acsp_vals.length ? _round2(acsp_vals.reduce((a, b) => a + b, 0) / acsp_vals.length) : null;
    frappe.model.set_value(cdt, cdn, "macsp", macsp);

    // MACS = mean([macsp (if exists)] + [each non-null ACSE])
    const acse_vals = [row.acse_1, row.acse_2].map(_num).filter(v => v !== null);
    const macs_inputs = (macsp !== null ? [macsp] : []).concat(acse_vals);
    const macs = macs_inputs.length ? _round2(macs_inputs.reduce((a, b) => a + b, 0) / macs_inputs.length) : null;
    frappe.model.set_value(cdt, cdn, "macs", macs);

    // MT = (2 × MACS + ACP) / 3
    const acp = _num(row.acp);
    const mt = (macs !== null && acp !== null) ? _round2((2 * macs + acp) / 3) : null;
    frappe.model.set_value(cdt, cdn, "mt", mt);
}

// ---------------------------------------------------------------------------
// Grid setup
// ---------------------------------------------------------------------------

function _setup_grid(frm) {
    const grid = frm.fields_dict["grade_rows"] && frm.fields_dict["grade_rows"].grid;
    if (!grid) return;
    grid.cannot_add_rows  = true;
    grid.cannot_delete_rows = true;
    grid.editable_grid = true;
}

// ---------------------------------------------------------------------------
// Sync students
// ---------------------------------------------------------------------------

function _sync_students(frm) {
    frappe.confirm(
        __("Alunos sem estado 'Activo' serão removidos da pauta. As notas dos restantes são preservadas. Continuar?"),
        () => {
            frappe.call({
                method: "escola.escola.doctype.grade_entry.grade_entry.sync_grade_entry_students",
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
                        frappe.show_alert({ message: __("Nenhuma alteração necessária."), indicator: "green" });
                    }
                },
            });
        }
    );
}

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
    frm.set_query("subject", () => ({ filters: { is_active: 1 } }));
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
        frappe.msgprint(__("Seleccione o Período antes de carregar alunos."));
        return;
    }

    const r = await frappe.call({
        method: "escola.escola.doctype.grade_entry.grade_entry.get_grade_entry_students",
        args: {
            class_group: frm.doc.class_group,
            academic_year: frm.doc.academic_year,
        },
    });

    if (!r.message) return;

    if (r.message.error === "no_students") {
        frappe.msgprint(
            __("Não foram encontrados alunos activos para a Turma <b>{0}</b>.", [frm.doc.class_group])
        );
        return;
    }

    if ((frm.doc.grade_rows || []).every(r => !r.student)) {
        frm.clear_table("grade_rows");
    }

    const existing = new Set((frm.doc.grade_rows || []).map(r => r.student));
    let added = 0;

    for (const s of r.message) {
        if (!existing.has(s.student)) {
            const row = frappe.model.add_child(frm.doc, "Grade Entry Row", "grade_rows");
            row.student = s.student;
            row.student_name = s.student_name;
            added++;
        }
    }

    frm.refresh_field("grade_rows");

    if (added > 0) {
        frappe.show_alert({ message: __("{0} aluno(s) adicionado(s).", [added]), indicator: "green" });
    } else {
        frappe.show_alert({ message: __("Todos os alunos já constam da pauta."), indicator: "blue" });
    }
}
