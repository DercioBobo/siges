frappe.ui.form.on("Academic Closure", {
    refresh(frm) {
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
});

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
