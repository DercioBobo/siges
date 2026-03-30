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
            const status = frm.doc.current_status;

            _set_financial_indicator(frm);
            _load_financial_summary(frm);
            _load_academic_history(frm);

            // ── Ver ──────────────────────────────────────────────────
            frm.add_custom_button(
                __("Boletins"),
                () => frappe.set_route("List", "Report Card", { student: frm.doc.name }),
                __("Ver")
            );
            frm.add_custom_button(
                __("Alocações na Turma"),
                () => frappe.set_route("List", "Student Group Assignment", { student: frm.doc.name }),
                __("Ver")
            );
            frm.add_custom_button(
                __("Inscrições"),
                () => frappe.set_route("List", "Inscricao", { student: frm.doc.name }),
                __("Ver")
            );
            frm.add_custom_button(
                __("Trocas de Turma"),
                () => frappe.set_route("List", "Troca de Turma", { student: frm.doc.name }),
                __("Ver")
            );
            frm.add_custom_button(
                __("Transferências"),
                () => frappe.set_route("List", "Student Transfer", { student: frm.doc.name }),
                __("Ver")
            );
            frm.add_custom_button(
                __("Facturas"),
                () => frappe.set_route("List", "Sales Invoice", { escola_student: frm.doc.name }),
                __("Ver")
            );

            // ── Acções ───────────────────────────────────────────────
            if (status === "Transferido" || status === "Desistente") {
                frm.add_custom_button(
                    __("Reactivar Aluno"),
                    () => reactivate_dialog(frm),
                    __("Acções")
                );
            }

            frm.add_custom_button(
                __("Nova Inscrição"),
                () => frappe.new_doc("Inscricao", { student: frm.doc.name }),
                __("Acções")
            );

            frm.add_custom_button(
                __("Nova Troca de Turma"),
                () => frappe.new_doc("Troca de Turma", { student: frm.doc.name }),
                __("Acções")
            );

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
        }
    },

    first_name(frm)    { update_full_name(frm); },
    last_name(frm)     { update_full_name(frm); },
    date_of_birth(frm) { update_age(frm); },
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
// Academic history panel
// ---------------------------------------------------------------------------

function _load_academic_history(frm) {
    const fd = frm.fields_dict["student_history_html"];
    if (!fd) return;

    fd.$wrapper.html(
        `<div style="color:#9ca3af;font-size:12px;padding:4px 0;">${__("A carregar historial...")}</div>`
    );

    frappe.call({
        method: "escola.escola.doctype.student.student.get_student_academic_history",
        args: { student: frm.doc.name },
        callback(r) {
            if (r.exc) {
                fd.$wrapper.html(
                    `<div style="color:#9ca3af;font-size:13px;">${__("Não foi possível carregar o historial.")}</div>`
                );
                return;
            }
            fd.$wrapper.html(_render_history(r.message || []));
        },
    });
}

function _render_history(data) {
    if (!data || !data.length) {
        return `<div style="color:#9ca3af;font-size:13px;padding:8px 0;">${__("Sem historial académico registado.")}</div>`;
    }

    const STATUS_STYLE = {
        "Activa":      { bg: "#f0fdf4", border: "#bbf7d0", badge_bg: "#dcfce7", badge_fg: "#16a34a" },
        "Transferida": { bg: "#fffbeb", border: "#fde68a", badge_bg: "#fef3c7", badge_fg: "#b45309" },
        "Encerrada":   { bg: "#f9fafb", border: "#e5e7eb", badge_bg: "#f3f4f6", badge_fg: "#6b7280" },
    };
    const RESULT_COLOR = {
        "Aprovado":  "#16a34a",
        "Reprovado": "#dc2626",
    };

    return data.map(yr => {
        const sc = STATUS_STYLE[yr.sga_status] || STATUS_STYLE["Encerrada"];
        const rc = RESULT_COLOR[yr.final_decision];

        const decisionHtml = yr.final_decision
            ? `<span style="color:${rc || "#374151"};font-weight:600;">${__(yr.final_decision)}</span>`
            : "";
        const avgHtml = yr.overall_average != null
            ? `<span style="color:#374151;">${__("Média")}: <b>${yr.overall_average}</b></span>`
            : "";
        const absHtml = yr.total_absences != null
            ? `<span style="color:#374151;">${__("Faltas")}: <b>${yr.total_absences}</b></span>`
            : "";

        const stats = [decisionHtml, avgHtml, absHtml].filter(Boolean);

        const rcLink = yr.report_card
            ? `<a href="/app/report-card/${encodeURIComponent(yr.report_card)}" target="_blank"
                  style="font-size:12px;color:#6366f1;text-decoration:none;">${__("Ver Boletim")} →</a>`
            : "";
        const cgLink = yr.class_group
            ? `<a href="/app/class-group/${encodeURIComponent(yr.class_group)}" target="_blank"
                  style="font-size:12px;color:#6366f1;text-decoration:none;margin-left:12px;">${__("Ver Turma")} →</a>`
            : "";

        return `
<div style="border:1px solid ${sc.border};border-radius:8px;margin-bottom:10px;overflow:hidden;">
  <div style="background:${sc.bg};padding:9px 14px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid ${sc.border};">
    <div style="display:flex;align-items:center;gap:10px;">
      <span style="font-weight:600;font-size:14px;">${yr.academic_year}</span>
      ${yr.sga_status ? `<span style="background:${sc.badge_bg};color:${sc.badge_fg};font-size:11px;font-weight:600;padding:2px 8px;border-radius:12px;">${__(yr.sga_status)}</span>` : ""}
    </div>
    ${yr.assignment_date ? `<span style="font-size:11px;color:#9ca3af;">${yr.assignment_date}</span>` : ""}
  </div>
  <div style="padding:10px 14px;">
    <div style="display:flex;gap:20px;flex-wrap:wrap;${stats.length ? "margin-bottom:8px;" : ""}">
      <div>
        <div style="font-size:10px;color:#9ca3af;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:2px;">${__("Classe")}</div>
        <div style="font-size:13px;font-weight:500;">${yr.school_class || "—"}</div>
      </div>
      <div>
        <div style="font-size:10px;color:#9ca3af;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:2px;">${__("Turma")}</div>
        <div style="font-size:13px;font-weight:500;">${yr.class_group || "—"}</div>
      </div>
    </div>
    ${stats.length ? `<div style="display:flex;gap:14px;flex-wrap:wrap;font-size:13px;">${stats.join('<span style="color:#d1d5db;">·</span>')}</div>` : ""}
  </div>
  ${(rcLink || cgLink) ? `
  <div style="padding:7px 14px;border-top:1px solid #f3f4f6;background:#fafafa;">
    ${rcLink}${cgLink}
  </div>` : ""}
</div>`;
    }).join("");
}

// ---------------------------------------------------------------------------
// Full name sync
// ---------------------------------------------------------------------------

function update_age(frm) {
    if (!frm.doc.date_of_birth) return;
    const dob = frappe.datetime.str_to_obj(frm.doc.date_of_birth);
    const today = new Date();
    let age = today.getFullYear() - dob.getFullYear();
    if (
        today.getMonth() < dob.getMonth() ||
        (today.getMonth() === dob.getMonth() && today.getDate() < dob.getDate())
    ) age--;
    frm.set_value("idade", age >= 0 ? age : null);
}

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
