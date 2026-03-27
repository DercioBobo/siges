frappe.ui.form.on("Fee Structure", {
    refresh(frm) {
        if (!frm.doc.__islocal) {
            _show_total(frm);
        }
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
