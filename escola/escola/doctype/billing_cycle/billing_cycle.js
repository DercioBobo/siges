frappe.ui.form.on("Billing Cycle", {
    refresh(frm) {
        set_queries(frm);
        frm.add_custom_button(__("Gerar Facturas"), () => {
            if (frm.doc.__islocal) {
                frappe.msgprint(__("Por favor, guarde o Ciclo de Facturação antes de gerar facturas."));
                return;
            }
            if (!frm.doc.billing_mode) {
                frappe.msgprint(__("Defina o Modo de Cobrança antes de gerar facturas."));
                return;
            }

            const already_generated = (frm.doc.total_invoices_created || 0) > 0;
            const msg = already_generated
                ? __("Este ciclo já gerou {0} factura(s). Serão criadas apenas facturas em falta (sem duplicar). Continuar?",
                     [frm.doc.total_invoices_created])
                : __("Serão geradas facturas para todos os alunos activos com atribuições de propinas "
                   + "com o modo de cobrança '{0}'. Continuar?", [frm.doc.billing_mode]);

            frappe.confirm(msg, () => {
                frappe.call({
                    method: "escola.escola.doctype.billing_cycle.billing_cycle.generate_invoices",
                    args: { doc_name: frm.doc.name },
                    freeze: true,
                    freeze_message: __("A gerar facturas..."),
                    callback(r) {
                        if (r.exc) return;
                        const { created, skipped, total_amount } = r.message;

                        if (created === 0 && skipped === 0) {
                            frappe.msgprint(__(
                                "Nenhuma factura foi criada. Verifique se existem Atribuições de Propinas "
                                + "activas com o modo '{0}' para este contexto.",
                                [frm.doc.billing_mode]
                            ));
                        } else {
                            frappe.msgprint(__(
                                "{0} factura(s) criada(s). {1} já existiam e foram ignoradas. "
                                + "Valor total gerado: {2}.",
                                [created, skipped, format_currency(total_amount)]
                            ));
                        }

                        frm.reload_doc();
                    },
                });
            });
        });

        // Show linked invoices button if cycle has been run
        if (!frm.doc.__islocal && (frm.doc.total_invoices_created || 0) > 0) {
            frm.add_custom_button(__("Ver Facturas"), () => {
                frappe.set_route("List", "Sales Invoice", {
                    escola_billing_cycle: frm.doc.name,
                });
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
