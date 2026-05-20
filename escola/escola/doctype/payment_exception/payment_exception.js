frappe.ui.form.on("Payment Exception", {
    refresh(frm) {
        if (frm.doc.is_active && frm.doc.applies_from && frm.doc.applies_until) {
            const today = frappe.datetime.get_today();
            const active = frm.doc.applies_from <= today && today <= frm.doc.applies_until;
            frm.dashboard.set_headline(
                active
                    ? `<span class="indicator-pill green">Em vigor</span>`
                    : `<span class="indicator-pill grey">Fora do período</span>`
            );
        }
    },
});
