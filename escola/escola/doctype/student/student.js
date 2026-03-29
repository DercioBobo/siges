// Copyright (c) 2024, EntreTech and contributors
// For license information, please see license.txt

const _FINANCIAL_COLORS = {
    "Regular":           "green",
    "Em Dívida":         "yellow",
    "Em Dívida Crítica": "orange",
    "Suspenso":          "red",
};

const _ALERT_MESSAGES = {
    1: "Pagamento em atraso",
    2: "Multa significativa aplicada",
    3: "Risco de suspensão",
    4: "Aluno elegível para suspensão",
};

frappe.ui.form.on("Student", {
    refresh(frm) {
        if (!frm.is_new()) {
            const current_status = frm.doc.current_status;

            _set_financial_indicator(frm);
            _load_financial_summary(frm);

            if (current_status === "Transferido" || current_status === "Desistente") {
                frm.add_custom_button(
                    __("Reactivar Aluno"),
                    () => reactivate_dialog(frm),
                    __("Acções")
                );
            }

            frm.add_custom_button(
                __("Registar Transferência"),
                () => frappe.new_doc("Student Transfer", { student: frm.doc.name }),
                __("Acções")
            );

            frm.add_custom_button(
                __("Actualizar Estado Financeiro"),
                () => {
                    frappe.call({
                        method: "escola.escola.doctype.billing_cycle.penalty.update_student_financial_status",
                        args: { student_name: frm.doc.name },
                        freeze: true,
                        freeze_message: __("A calcular estado financeiro..."),
                        callback(r) {
                            if (r.exc) return;
                            frm.reload_doc();
                        },
                    });
                },
                __("Acções")
            );

            frm.add_custom_button(
                __("Ver Transferências"),
                () => frappe.set_route("List", "Student Transfer", { student: frm.doc.name }),
                __("Ver")
            );

            frm.add_custom_button(
                __("Ver Facturas"),
                () => frappe.set_route("List", "Sales Invoice", { escola_student: frm.doc.name }),
                __("Ver")
            );
        }
    },

    first_name(frm) { update_full_name(frm); },
    last_name(frm)  { update_full_name(frm); },
});

// ---------------------------------------------------------------------------
// Financial status helpers
// ---------------------------------------------------------------------------

function _set_financial_indicator(frm) {
    const status = frm.doc.financial_status || "Regular";
    const color  = _FINANCIAL_COLORS[status] || "gray";
    frm.page.set_indicator(__(status), color);
}

function _load_financial_summary(frm) {
    frappe.call({
        method: "escola.escola.doctype.billing_cycle.penalty.get_student_financial_summary",
        args: { student_name: frm.doc.name },
        callback(r) {
            if (r.exc || !r.message) return;
            const d = r.message;

            if (d.alert_level === 0) {
                frm.dashboard.set_headline("");
                return;
            }

            const color = _FINANCIAL_COLORS[d.financial_status] || "gray";
            const alert_text = __(_ALERT_MESSAGES[d.alert_level] || "");

            const parts = [
                `<b style="color:var(--${color}-600)">${alert_text}</b>`,
                __("Em dívida: {0}", [format_currency(d.total_outstanding)]),
            ];

            if (d.penalty_rate > 0) {
                parts.push(__("Multa: {0}% = {1}", [d.penalty_rate, format_currency(d.penalty_amount)]));
            }
            if (d.days_overdue > 0) {
                parts.push(__("{0} dias em atraso ({1} período(s))", [d.days_overdue, d.periods]));
            }
            if (d.total_with_penalty > d.total_outstanding) {
                parts.push(__("Total com multa: {0}", [format_currency(d.total_with_penalty)]));
            }

            frm.dashboard.set_headline(parts.join(" &nbsp;|&nbsp; "));
        },
    });
}

// ---------------------------------------------------------------------------
// Full name sync
// ---------------------------------------------------------------------------

function update_full_name(frm) {
    const parts = [frm.doc.first_name, frm.doc.last_name].filter(Boolean);
    frm.set_value("full_name", parts.join(" "));
}

// ---------------------------------------------------------------------------
// Reactivation dialog
// ---------------------------------------------------------------------------

function reactivate_dialog(frm) {
    const d = new frappe.ui.Dialog({
        title: __("Reactivar {0}", [frm.doc.full_name]),
        fields: [
            {
                fieldname: "academic_year",
                fieldtype: "Link",
                options: "Academic Year",
                label: __("Ano Lectivo"),
                reqd: 1,
                onchange() {
                    d.set_value("class_group", null);
                    d.fields_dict.class_group.get_query = () => ({
                        filters: build_filters(d),
                    });
                },
            },
            {
                fieldname: "school_class",
                fieldtype: "Link",
                options: "School Class",
                label: __("Classe"),
                get_query: () => ({ filters: { is_active: 1 } }),
                onchange() {
                    d.set_value("class_group", null);
                    d.fields_dict.class_group.get_query = () => ({
                        filters: build_filters(d),
                    });
                },
            },
            {
                fieldname: "class_group",
                fieldtype: "Link",
                options: "Class Group",
                label: __("Turma"),
                reqd: 1,
                get_query: () => ({ filters: build_filters(d) }),
                description: __("Seleccione a turma para o ano lectivo em curso."),
            },
        ],
        primary_action_label: __("Reactivar"),
        primary_action(values) {
            frappe.call({
                method: "escola.escola.doctype.inscricao.inscricao.reactivate_student",
                args: {
                    student_name: frm.doc.name,
                    class_group_name: values.class_group,
                },
                callback(r) {
                    if (r.exc) return;
                    d.hide();
                    frappe.show_alert({
                        message: __("Aluno reactivado e atribuído à turma."),
                        indicator: "green",
                    });
                    frm.reload_doc();
                },
            });
        },
    });
    d.show();
}

function build_filters(d) {
    const f = { is_active: 1 };
    const ay = d.get_value("academic_year");
    const sc = d.get_value("school_class");
    if (ay) f.academic_year = ay;
    if (sc) f.school_class = sc;
    return f;
}
