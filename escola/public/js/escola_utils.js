window.escola = window.escola || {};
escola.utils = escola.utils || {};

/**
 * Fetch the current Academic Year from the server and set it on frm.
 * Only runs on new (unsaved) documents where the field is still empty.
 */
escola.utils.auto_fill_academic_year = function (frm, fieldname) {
    fieldname = fieldname || "academic_year";
    if (!frm.doc.__islocal || frm.doc[fieldname]) return;

    frappe.call({
        method: "escola.escola.doctype.grade_entry.grade_entry.get_current_academic_year",
        callback(r) {
            if (r.message && !frm.doc[fieldname]) {
                frm.set_value(fieldname, r.message);
            }
        },
    });
};
