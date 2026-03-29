frappe.ui.form.on("Fee Structure", {
    refresh(frm) {
        if (!frm.doc.__islocal) {
            _show_total(frm);

            frm.add_custom_button(__("Gerar Atribuições de Propinas"), () => {
                frappe.confirm(
                    __("Serão criadas Atribuições de Propinas para todos os alunos activos "
                     + "da Classe <b>{0}</b> no Ano Lectivo <b>{1}</b> que ainda não tenham "
                     + "uma atribuição activa. Continuar?", [frm.doc.school_class, frm.doc.academic_year]),
                    () => {
                        frappe.call({
                            method: "escola.escola.doctype.fee_structure.fee_structure.generate_assignments",
                            args: { fee_structure_name: frm.doc.name },
                            freeze: true,
                            freeze_message: __("A criar atribuições..."),
                            callback(r) {
                                if (r.exc) return;
                                const { created, skipped, errors } = r.message;
                                let msg = __("{0} atribuição(ões) criada(s). {1} já existiam e foram ignoradas.",
                                    [created, skipped]);
                                if (errors && errors.length) {
                                    msg += "<br><b>" + __("{0} erro(s):", [errors.length]) + "</b><br>";
                                    msg += errors.map(e => `${e.student}: ${e.error}`).join("<br>");
                                }
                                frappe.msgprint({ message: msg, title: __("Resultado"), indicator: created > 0 ? "green" : "orange" });
                            },
                        });
                    }
                );
            });
        }

        frm.set_query("school_class", () => ({ filters: { is_active: 1 } }));
    },

    fee_lines_add(frm) { _show_total(frm); },
    fee_lines_remove(frm) { _show_total(frm); },
});

frappe.ui.form.on("Fee Structure Line", {
    amount(frm) { _show_total(frm); },
});

function _show_total(frm) {
    const total = (frm.doc.fee_lines || []).reduce((sum, r) => sum + (r.amount || 0), 0);
    frm.dashboard.set_headline(
        __("Total do Plano: {0}", [format_currency(total)])
    );
}
