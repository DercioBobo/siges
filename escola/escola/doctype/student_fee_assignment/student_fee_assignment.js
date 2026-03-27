frappe.ui.form.on("Student Fee Assignment", {
    refresh(frm) {
        frm.add_custom_button(__("Carregar do Plano"), () => {
            if (!frm.doc.fee_structure) {
                frappe.msgprint(__("Seleccione primeiro um Plano de Propinas."));
                return;
            }
            if (frm.doc.__islocal) {
                frappe.msgprint(__("Por favor, guarde o documento antes de carregar o plano."));
                return;
            }

            const do_load = () => {
                frappe.call({
                    method: "escola.escola.doctype.student_fee_assignment.student_fee_assignment.load_from_structure",
                    args: { doc_name: frm.doc.name },
                    callback(r) {
                        if (r.exc) return;
                        const data = r.message;

                        if (data.error === "no_structure") {
                            frappe.msgprint(__("Nenhum Plano de Propinas seleccionado."));
                            return;
                        }
                        if (data.error === "no_lines") {
                            frappe.msgprint(__("O Plano de Propinas seleccionado não tem linhas."));
                            return;
                        }

                        frm.clear_table("assignment_lines");
                        (data.lines || []).forEach((ln) => {
                            const child = frm.add_child("assignment_lines");
                            child.fee_category = ln.fee_category;
                            child.item_code = ln.item_code;
                            child.description = ln.description || "";
                            child.amount = ln.amount;
                            child.billing_mode = ln.billing_mode;
                            child.is_optional = 0;
                        });

                        frm.refresh_field("assignment_lines");
                        frm.dirty();
                        frappe.show_alert({ message: __("Linhas carregadas do Plano."), indicator: "green" });
                    },
                });
            };

            if (frm.doc.assignment_lines && frm.doc.assignment_lines.length > 0) {
                frappe.confirm(
                    __("Já existem linhas na Atribuição. Deseja substituí-las pelas linhas do Plano?"),
                    do_load
                );
            } else {
                do_load();
            }
        });

        frm.add_custom_button(__("Criar / Vincular Cliente"), () => {
            if (!frm.doc.student) {
                frappe.msgprint(__("Seleccione primeiro um Aluno."));
                return;
            }
            if (frm.doc.__islocal) {
                frappe.msgprint(__("Por favor, guarde o documento antes de criar o Cliente."));
                return;
            }

            frappe.call({
                method: "escola.escola.doctype.student_fee_assignment.student_fee_assignment.ensure_customer",
                args: { doc_name: frm.doc.name },
                callback(r) {
                    if (r.exc) return;
                    const data = r.message;
                    if (data.error === "no_student") {
                        frappe.msgprint(__("Nenhum aluno seleccionado na Atribuição."));
                        return;
                    }
                    frm.set_value("customer", data.customer);
                    frappe.show_alert({
                        message: __("Cliente vinculado: {0}", [data.customer]),
                        indicator: "green",
                    });
                },
            });
        });
    },

    student(frm) {
        if (!frm.doc.student || !frm.doc.academic_year) return;

        // Try to fetch active class group for this student + academic year
        frappe.db.get_value(
            "Student Group Assignment",
            {
                student: frm.doc.student,
                academic_year: frm.doc.academic_year,
                status: "Activa",
            },
            "class_group",
            (r) => {
                if (!r || !r.class_group) return;
                frm.set_value("class_group", r.class_group);

                frappe.db.get_value("Class Group", r.class_group, "school_class", (r2) => {
                    if (r2 && r2.school_class) {
                        frm.set_value("school_class", r2.school_class);
                    }
                });
            }
        );
    },

    academic_year(frm) {
        // Re-trigger student context fetch when academic year changes
        if (frm.doc.student) {
            frm.trigger("student");
        }
    },
});
