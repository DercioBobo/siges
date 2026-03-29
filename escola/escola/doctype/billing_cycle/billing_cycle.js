frappe.ui.form.on("Billing Cycle", {
    refresh(frm) {
        set_queries(frm);

        if (frm.doc.__islocal) {
            _suggest_dates(frm);
            return;
        }

        if (frm.doc.status !== "Cancelado") {
            frm.add_custom_button(__("Gerar Facturas"), () => {
                if (!frm.doc.billing_mode) {
                    frappe.msgprint(__("Defina o Modo de Cobrança antes de gerar facturas."));
                    return;
                }
                const already = (frm.doc.total_invoices_created || 0) > 0;
                const msg = already
                    ? __("Este ciclo já gerou {0} factura(s). Serão criadas apenas facturas em falta. Continuar?",
                         [frm.doc.total_invoices_created])
                    : __("Serão geradas facturas para todos os alunos activos da Classe '{0}' com propinas no modo '{1}'. Continuar?",
                         [frm.doc.school_class, frm.doc.billing_mode]);

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
                                frappe.msgprint(__("Nenhuma factura criada. Verifique se existe um Plano de Propinas activo para a Classe e se há alunos matriculados."));
                            } else {
                                frappe.msgprint(__("{0} factura(s) criada(s), {1} ignorada(s). Total: {2}.",
                                    [created, skipped, format_currency(total_amount)]));
                            }
                            frm.reload_doc();
                        },
                    });
                });
            });

            frm.add_custom_button(__("Aplicar Multas"), () => {
                frappe.db.get_single_value("School Settings", "penalty_mode").then(mode => {
                    if (mode !== "Adicionar à Factura") {
                        frappe.msgprint({
                            message: __("O modo de multa está configurado como <b>Dinâmico</b>. "
                                      + "As multas são calculadas e apresentadas mas não são adicionadas às facturas. "
                                      + "Para adicionar à factura, altere nas Configurações da Escola."),
                            title: __("Modo Dinâmico"),
                            indicator: "blue",
                        });
                        return;
                    }

                    const count = frm.doc.total_invoices_created || 0;
                    frappe.confirm(
                        __("Serão calculadas e adicionadas linhas de multa às {0} factura(s) em Rascunho deste ciclo. "
                         + "A operação é idempotente — multas anteriores são substituídas. Continuar?", [count]),
                        () => {
                            frappe.call({
                                method: "escola.escola.doctype.billing_cycle.penalty.apply_penalties_for_cycle",
                                args: { billing_cycle_name: frm.doc.name },
                                freeze: true,
                                freeze_message: __("A calcular multas..."),
                                callback(r) {
                                    if (r.exc) return;
                                    const { applied, skipped, errors } = r.message;
                                    let msg = __("{0} factura(s) com multa aplicada. {1} sem atraso (ignoradas).",
                                        [applied, skipped]);
                                    if (errors && errors.length) {
                                        msg += "<br><b>" + __("{0} erro(s):", [errors.length]) + "</b><br>";
                                        msg += errors.map(e => `${e.invoice}: ${e.error}`).join("<br>");
                                    }
                                    frappe.msgprint({ message: msg, title: __("Multas Aplicadas"),
                                        indicator: applied > 0 ? "orange" : "green" });
                                    frm.reload_doc();
                                },
                            });
                        }
                    );
                });
            }, __("Acções"));

            frm.add_custom_button(__("Cancelar Ciclo"), () => {
                const count = frm.doc.total_invoices_created || 0;
                frappe.confirm(
                    __("Esta acção irá cancelar/eliminar as {0} factura(s) deste ciclo. "
                     + "Não pode ser desfeita. Continuar?", [count]),
                    () => {
                        frappe.call({
                            method: "escola.escola.doctype.billing_cycle.billing_cycle.cancel_cycle",
                            args: { doc_name: frm.doc.name },
                            freeze: true,
                            freeze_message: __("A cancelar facturas..."),
                            callback(r) {
                                if (r.exc) return;
                                const { cancelled, deleted, errors } = r.message;
                                let msg = __("{0} cancelada(s), {1} eliminada(s).", [cancelled, deleted]);
                                if (errors && errors.length) {
                                    msg += "<br>" + errors.join("<br>");
                                }
                                frappe.msgprint({ message: msg, title: __("Ciclo cancelado"), indicator: "orange" });
                                frm.reload_doc();
                            },
                        });
                    }
                );
            }, __("Acções"));
        }

        if ((frm.doc.total_invoices_created || 0) > 0) {
            frm.add_custom_button(__("Ver Facturas"), () => {
                frappe.set_route("List", "Sales Invoice", { escola_billing_cycle: frm.doc.name });
            }, __("Ver"));
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

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function set_queries(frm) {
    const cg_filters = { is_active: 1 };
    if (frm.doc.academic_year) cg_filters.academic_year = frm.doc.academic_year;
    if (frm.doc.school_class)  cg_filters.school_class  = frm.doc.school_class;
    frm.set_query("class_group",  () => ({ filters: cg_filters }));
    frm.set_query("school_class", () => ({ filters: { is_active: 1 } }));
}

function _suggest_dates(frm) {
    frappe.db.get_value(
        "School Settings", "School Settings",
        ["invoice_posting_day", "payment_due_day"],
        (r) => {
            if (!r) return;
            const posting_day = parseInt(r.invoice_posting_day) || 25;
            const due_day     = parseInt(r.payment_due_day) || 10;

            const now = new Date();
            let p_month = now.getMonth();   // 0-indexed
            let p_year  = now.getFullYear();

            // If we're already past posting_day this month, use next month
            if (now.getDate() > posting_day) {
                p_month += 1;
                if (p_month > 11) { p_month = 0; p_year++; }
            }

            // due date: due_day of the month after posting month
            let d_month = p_month + 1;
            let d_year  = p_year;
            if (d_month > 11) { d_month = 0; d_year++; }

            const posting = frappe.datetime.obj_to_str(new Date(p_year, p_month, posting_day));
            const due     = frappe.datetime.obj_to_str(new Date(d_year, d_month, due_day));

            if (!frm.doc.posting_date) frm.set_value("posting_date", posting);
            if (!frm.doc.due_date)     frm.set_value("due_date", due);
        }
    );
}
