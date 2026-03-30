frappe.ui.form.on("Academic Closure", {
    onload(frm) {
        escola.utils.auto_fill_academic_year(frm);
    },

    refresh(frm) {
        set_queries(frm);
        frm.add_custom_button(__("Carregar Promoções"), () => {
            if (!frm.doc.academic_year || !frm.doc.class_group) {
                frappe.msgprint(__("Por favor, preencha o Ano Lectivo e a Turma antes de carregar."));
                return;
            }
            if (frm.doc.__islocal) {
                frappe.msgprint(__("Por favor, guarde o documento antes de carregar."));
                return;
            }

            const do_load = () => {
                frappe.call({
                    method: "escola.escola.doctype.academic_closure.academic_closure.load_promotions",
                    args: { doc_name: frm.doc.name },
                    callback(r) {
                        if (!r.exc) {
                            _apply_promotion_data(frm, r.message);
                        }
                    },
                });
            };

            if (frm.doc.closure_rows && frm.doc.closure_rows.length > 0) {
                frappe.confirm(
                    __("Já existem dados no Fecho. Deseja substituir os dados actuais?"),
                    do_load
                );
            } else {
                do_load();
            }
        });

        if (!frm.doc.__islocal && frm.doc.closure_rows && frm.doc.closure_rows.length > 0) {
            frm.add_custom_button(__("Criar Boletins"), () => {
                frappe.confirm(
                    __("Serão criados Boletins para os alunos desta turma que ainda não tenham um. Continuar?"),
                    () => {
                        frappe.call({
                            method: "escola.escola.doctype.academic_closure.academic_closure.create_report_cards",
                            args: { doc_name: frm.doc.name },
                            callback(r) {
                                if (r.exc) return;
                                const msg = r.message;
                                if (msg.error === "no_closure_rows") {
                                    frappe.msgprint(__("Não existem alunos no Fecho para criar Boletins."));
                                    return;
                                }
                                const created = (msg.created || []).length;
                                const skipped = (msg.skipped || []).length;
                                if (created > 0) {
                                    frappe.show_alert({
                                        message: __(
                                            "{0} Boletim(ns) criado(s). {1} já existiam e foram ignorados.",
                                            [created, skipped]
                                        ),
                                        indicator: "green",
                                    });
                                } else {
                                    frappe.msgprint(__("Todos os alunos desta turma já possuem um Boletim."));
                                }
                            },
                        });
                    }
                );
            }, __("Acções"));
        }
    },

    academic_year(frm) {
        frm.set_value("school_class", null);
        frm.set_value("class_group", null);
        set_queries(frm);
    },

    school_class(frm) {
        frm.set_value("class_group", null);
        set_queries(frm);
    },
});

function set_queries(frm) {
    const cg_filters = { is_active: 1 };
    if (frm.doc.academic_year) cg_filters.academic_year = frm.doc.academic_year;
    if (frm.doc.school_class) cg_filters.school_class = frm.doc.school_class;
    frm.set_query("class_group", () => ({ filters: cg_filters }));
    frm.set_query("school_class", () => ({ filters: { is_active: 1 } }));
}

function _apply_promotion_data(frm, data) {
    if (!data) return;

    if (data.error === "no_promotion") {
        frappe.msgprint(__("Não existe Promoção de Alunos para esta Turma e Ano Lectivo."));
        return;
    }
    if (data.error === "no_rows") {
        frappe.msgprint(__("Não foram encontrados dados de promoção para esta Turma."));
        return;
    }

    frm.clear_table("closure_rows");
    (data.rows || []).forEach((row) => {
        const child = frm.add_child("closure_rows");
        child.student = row.student;
        child.final_decision = row.final_decision;
        child.total_failed_subjects = row.total_failed_subjects;
        child.overall_average = row.overall_average;
        child.remarks = row.remarks || "";
    });

    frm.refresh_field("closure_rows");
    frm.dirty();
    frappe.show_alert({ message: __("Promoções carregadas com sucesso."), indicator: "green" });
}
