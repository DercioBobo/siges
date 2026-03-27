frappe.ui.form.on("Report Card", {
    refresh(frm) {
        frm.add_custom_button(__("Carregar Avaliação"), () => {
            if (!frm.doc.student || !frm.doc.academic_year || !frm.doc.class_group) {
                frappe.msgprint(__(
                    "Por favor, preencha o Aluno, o Ano Lectivo e a Turma antes de carregar a avaliação."
                ));
                return;
            }
            if (frm.doc.__islocal) {
                frappe.msgprint(__("Por favor, guarde o documento antes de carregar a avaliação."));
                return;
            }

            const do_load = () => {
                frappe.call({
                    method: "escola.escola.doctype.report_card.report_card.load_assessment",
                    args: { doc_name: frm.doc.name },
                    callback(r) {
                        if (!r.exc) {
                            _apply_assessment_data(frm, r.message);
                        }
                    },
                });
            };

            if (frm.doc.report_card_rows && frm.doc.report_card_rows.length > 0) {
                frappe.confirm(
                    __("Já existem dados no Boletim. Deseja substituir os dados actuais?"),
                    do_load
                );
            } else {
                do_load();
            }
        });
    },

    student(frm) {
        if (frm.doc.student) {
            frappe.db.get_value("Student", frm.doc.student, "primary_guardian", (r) => {
                if (r && r.primary_guardian) {
                    frm.set_value("primary_guardian", r.primary_guardian);
                }
            });
        }
    },
});

function _apply_assessment_data(frm, data) {
    if (!data) return;

    if (data.error === "no_annual_assessment") {
        frappe.msgprint(__("Não existe Avaliação Anual para esta Turma e Ano Lectivo."));
        return;
    }
    if (data.error === "no_student_data") {
        frappe.msgprint(__("Não foram encontrados dados de avaliação para este aluno na Turma seleccionada."));
        return;
    }

    frm.clear_table("report_card_rows");
    (data.rows || []).forEach((row) => {
        const child = frm.add_child("report_card_rows");
        child.subject = row.subject;
        child.final_grade = row.final_grade;
        child.result = row.result;
        child.remarks = row.remarks || "";
    });

    if (data.final_decision) {
        frm.set_value("final_decision", data.final_decision);
    }
    if (data.primary_guardian && !frm.doc.primary_guardian) {
        frm.set_value("primary_guardian", data.primary_guardian);
    }

    frm.refresh_field("report_card_rows");
    frm.dirty();
    frappe.show_alert({ message: __("Avaliação carregada com sucesso."), indicator: "green" });
}
