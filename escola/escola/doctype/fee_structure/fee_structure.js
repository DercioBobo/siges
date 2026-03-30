frappe.ui.form.on("Fee Structure", {
    onload(frm) {
        escola.utils.auto_fill_academic_year(frm);
    },

    refresh(frm) {
        frm.set_query("school_class", () => ({ filters: { is_active: 1 } }));

        if (!frm.doc.__islocal) {
            _show_total(frm);
        }
    },

    fee_lines_add(frm) { _show_total(frm); },
    fee_lines_remove(frm) { _show_total(frm); },
});

frappe.ui.form.on("Fee Structure Line", {
    amount(frm) { _show_total(frm); },

    before_fee_lines_add(frm, cdt, cdn) {
        frappe.db.get_single_value("School Settings", "default_fee_item_code").then(item_code => {
            if (item_code) {
                frappe.model.set_value(cdt, cdn, "item_code", item_code);
            }
        });
    },
});

function _show_total(frm) {
    const total = (frm.doc.fee_lines || []).reduce((sum, r) => sum + (r.amount || 0), 0);
    frm.dashboard.set_headline(
        __("Total do Plano: {0}", [format_currency(total)])
    );
}
