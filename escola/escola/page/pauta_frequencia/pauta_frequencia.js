frappe.pages["pauta-frequencia"].on_page_load = function (wrapper) {
    const page = frappe.ui.make_app_page({
        parent: wrapper,
        title: __("Pauta de Frequência"),
        single_column: true,
    });
    new PautaFrequencia(page, wrapper);
};

// ---------------------------------------------------------------------------

class PautaFrequencia {
    constructor(page, wrapper) {
        this.page    = page;
        this.wrapper = wrapper;
        this.data    = null;

        this._inject_styles();
        this._build_skeleton();
        this.page.add_button(__("Imprimir"), () => {
            if (!this.data) { frappe.msgprint(__("Gere a pauta primeiro.")); return; }
            this._print();
        }, { icon: "fa fa-print" });
        this._load_filter_options();
    }

    // -----------------------------------------------------------------------
    // Setup
    // -----------------------------------------------------------------------

    _inject_styles() {
        if (document.getElementById("pf-styles")) return;
        const s = document.createElement("style");
        s.id = "pf-styles";
        s.textContent = `
            .pf-label { font-size:11px;color:#6B7280;font-weight:700;display:block;
                        margin-bottom:4px;letter-spacing:.5px; }
            .pf-preview-wrap { overflow-x:auto;margin-top:20px;border:1px solid #E5E7EB;border-radius:8px; }
            .pf-table { border-collapse:collapse;font-size:10px;min-width:100%; }
            .pf-table th, .pf-table td { border:1px solid #CBD5E1;padding:3px 4px;text-align:center;white-space:nowrap; }
            .pf-table th { background:#1E293B;color:#fff;font-size:9px;font-weight:700; }
            .pf-table th.subj-header { background:#2D3748; }
            .pf-table th.faltas-header { background:#4A5568; }
            .pf-table th.annual-header { background:#1A3A5C; }
            .pf-table td.name-cell { text-align:left;max-width:140px;overflow:hidden;text-overflow:ellipsis; }
            .pf-table td.aprovado { color:#059669;font-weight:700; }
            .pf-table td.reprovado { color:#DC2626;font-weight:700; }
            .pf-table td.avg-cell { background:#EFF6FF;font-weight:700;color:#1D4ED8; }
            .pf-table td.global-avg { background:#DBEAFE;font-weight:700;color:#1E40AF; }
            .pf-table tr:nth-child(even) td { background:#F8FAFC; }
            .pf-table tr:nth-child(even) td.avg-cell { background:#DBEAFE; }
            .pf-table tr:nth-child(even) td.global-avg { background:#BFDBFE; }
            .pf-stats { margin-top:24px; }
            .pf-stats-table { border-collapse:collapse;font-size:10px;width:100%; }
            .pf-stats-table th, .pf-stats-table td { border:1px solid #CBD5E1;padding:3px 6px;text-align:center; }
            .pf-stats-table th { background:#374151;color:#fff;font-size:9px; }
            .pf-stats-table td.label-cell { text-align:left;font-weight:600;background:#F9FAFB; }
        `;
        document.head.appendChild(s);
    }

    _build_skeleton() {
        const $body = $(this.wrapper).find(".page-content");
        $body.empty();
        this.$root = $(`
            <div style="padding:0 20px 60px;">
                <div class="pf-filters" style="padding:18px 0 12px;"></div>
                <div class="pf-body"></div>
            </div>
        `).appendTo($body);
        this.$filters = this.$root.find(".pf-filters");
        this.$body    = this.$root.find(".pf-body");
    }

    // -----------------------------------------------------------------------
    // Filters
    // -----------------------------------------------------------------------

    _load_filter_options() {
        frappe.call({
            method: "escola.escola.page.pauta_frequencia.pauta_frequencia.get_filter_options",
            callback: (r) => {
                if (r.message) this._render_filters(r.message);
            },
        });
    }

    _render_filters({ class_groups, years }) {
        this._cg_year_map = {};
        class_groups.forEach(c => { this._cg_year_map[c.name] = c.academic_year; });

        this.$filters.html(`
            <div style="display:flex;gap:16px;align-items:flex-end;flex-wrap:wrap;padding:18px 0 12px;">
                <div style="min-width:220px;" id="pf-ctrl-cg"></div>
                <div style="min-width:180px;" id="pf-ctrl-year"></div>
            </div>`);

        this._cg_ctrl = escola.utils.make_filter_select(
            this.$filters.find("#pf-ctrl-cg")[0],
            { label: __("TURMA"), placeholder: __("Pesquisar turma…"),
              options: class_groups.map(c => ({ value: c.name, label: c.group_name })) }
        );
        this._year_ctrl = escola.utils.make_filter_select(
            this.$filters.find("#pf-ctrl-year")[0],
            { label: __("ANO LECTIVO"), placeholder: __("Selecionar ano…"),
              options: years.map(y => ({ value: y.name, label: y.year_name || y.name })) }
        );

        this._cg_ctrl.on_change(cg => {
            const yr = this._cg_year_map[cg];
            if (yr) this._year_ctrl.set_value(yr);
            this._maybe_load();
        });
        this._year_ctrl.on_change(() => this._maybe_load());

    }

    _maybe_load() {
        if (this._cg_ctrl.get_value() && this._year_ctrl.get_value()) this._load();
    }

    // -----------------------------------------------------------------------
    // Data loading
    // -----------------------------------------------------------------------

    _load() {
        const cg   = this._cg_ctrl.get_value();
        const year = this._year_ctrl.get_value();
        if (!cg || !year) return;

        this.$body.html(`
            <div style="text-align:center;padding:60px;color:#9CA3AF;">
                <i class="fa fa-spinner fa-spin fa-2x"></i>
                <div style="margin-top:12px;font-size:14px;">A gerar pauta…</div>
            </div>
        `);

        frappe.call({
            method: "escola.escola.page.pauta_frequencia.pauta_frequencia.get_pauta_data",
            args: { class_group: cg, academic_year: year },
            callback: (r) => {
                if (r.exc) { this.$body.empty(); return; }
                this.data = r.message;
                this._render();
            },
        });
    }

    // -----------------------------------------------------------------------
    // Preview render
    // -----------------------------------------------------------------------

    _render() {
        const d = this.data;
        if (!d) return;

        if (!d.subjects || !d.subjects.length) {
            this.$body.html(this._empty_state("fa-book", "Sem currículo activo",
                `A Turma <b>${frappe.utils.escape_html(d.class_group_name)}</b> não tem currículo com disciplinas.`));
            return;
        }
        if (!d.students || !d.students.length) {
            this.$body.html(this._empty_state("fa-users", "Sem alunos activos",
                `A Turma <b>${frappe.utils.escape_html(d.class_group_name)}</b> não tem alunos inscritos.`));
            return;
        }

        const headerHtml = `
            <div style="margin-bottom:12px;">
                <div style="font-size:13px;font-weight:700;color:#1E293B;">
                    ${frappe.utils.escape_html(d.school_name)}
                </div>
                <div style="font-size:12px;color:#4B5563;margin-top:2px;">
                    Pauta de Frequência &mdash;
                    ${frappe.utils.escape_html(d.class_group_name)}
                    ${d.classroom ? "· Sala " + frappe.utils.escape_html(d.classroom) : ""}
                    &mdash; ${frappe.utils.escape_html(d.academic_year)}
                </div>
            </div>
        `;

        this.$body.html(
            headerHtml +
            `<div class="pf-preview-wrap">${this._build_table_html(d)}</div>` +
            `<div class="pf-stats">${this._build_stats_html(d)}</div>`
        );
    }

    _empty_state(icon, title, msg) {
        return `
            <div style="text-align:center;padding:70px 20px;background:#F9FAFB;
                        border-radius:12px;border:1px dashed #E5E7EB;margin-top:20px;">
                <i class="fa ${icon} fa-3x" style="color:#D1D5DB;"></i>
                <h3 style="color:#374151;margin-top:16px;">${title}</h3>
                <p style="color:#6B7280;">${msg}</p>
            </div>`;
    }

    // -----------------------------------------------------------------------
    // Table HTML
    // -----------------------------------------------------------------------

    _build_table_html(d) {
        const subjects = d.subjects;
        const terms    = d.terms;
        const n        = terms.length;

        // ---- header row 1: group labels ----
        let th1 = `<th rowspan="3">#</th>
                   <th rowspan="3" style="min-width:120px;">Nome</th>
                   <th rowspan="3">G</th>`;

        subjects.forEach(s => {
            th1 += `<th colspan="${n + n + n}" class="subj-header">
                        ${frappe.utils.escape_html(s.subject_code || s.subject_name)}
                    </th>`;
        });
        th1 += `<th colspan="${n}" class="subj-header">PORTAME</th>`;
        th1 += `<th colspan="${subjects.length + 1}" class="annual-header">MÉDIAS ANUAIS</th>`;
        th1 += `<th rowspan="3" class="annual-header">RESULTADO</th>`;

        // ---- header row 2: grades / faltas sub-labels ----
        let th2 = "";
        subjects.forEach(() => {
            th2 += `<th colspan="${n}">Notas</th>
                    <th colspan="${n}" class="faltas-header">F</th>
                    <th colspan="${n}" class="faltas-header">J</th>`;
        });
        // portame
        th2 += `<th colspan="${n}" class="subj-header">T</th>`;
        // annual per-subject + global
        subjects.forEach(s => {
            th2 += `<th class="annual-header">${frappe.utils.escape_html(s.subject_code || s.subject_name)}</th>`;
        });
        th2 += `<th class="annual-header">MG</th>`;

        // ---- header row 3: term labels ----
        let th3 = "";
        subjects.forEach(() => {
            for (let i = 0; i < 3; i++) {   // notas, faltas-inj, faltas-just
                terms.forEach((t, ti) => {
                    th3 += `<th>${ti + 1}</th>`;
                });
            }
        });
        terms.forEach((t, ti) => { th3 += `<th>${ti + 1}</th>`; });
        // annual averages columns have no sub-row label (already labelled in row 2)
        subjects.forEach(() => { th3 += `<th></th>`; });
        th3 += `<th></th>`;

        // ---- student rows ----
        const _v  = (v) => { const n = parseFloat(v); return (!isNaN(n) && v !== null && v !== undefined) ? String(Math.round(n)) : ""; };
        const _i  = (v) => (v !== null && v !== undefined) ? v : "";

        const rows_html = d.students.map(s => {
            let cells = `
                <td style="color:#9CA3AF;font-size:9px;">${s.idx}</td>
                <td class="name-cell" title="${frappe.utils.escape_html(s.student_name)}">
                    ${frappe.utils.escape_html(s.student_name)}
                </td>
                <td>${frappe.utils.escape_html(s.gender ? s.gender[0] : "")}</td>
            `;

            subjects.forEach(subj => {
                // Grades per term
                for (let p = 1; p <= n; p++) {
                    cells += `<td>${_v(s.grades[subj.name] && s.grades[subj.name][p])}</td>`;
                }
                // Unjustified absences per term
                for (let p = 1; p <= n; p++) {
                    const abs = s.absences[p];
                    cells += `<td>${_i(abs && abs.unjustified)}</td>`;
                }
                // Justified absences per term
                for (let p = 1; p <= n; p++) {
                    const abs = s.absences[p];
                    cells += `<td>${_i(abs && abs.justified)}</td>`;
                }
            });

            // Portamento per term
            for (let p = 1; p <= n; p++) {
                const comp = s.comportamento[p] || "";
                cells += `<td style="font-size:8px;">${frappe.utils.escape_html(_abbr_comp(comp))}</td>`;
            }

            // Annual averages per subject
            subjects.forEach(subj => {
                cells += `<td class="avg-cell">${_v(s.annual_subject_avgs[subj.name])}</td>`;
            });

            // Global average
            cells += `<td class="global-avg">${_v(s.global_average)}</td>`;

            // Result
            const res_cls = s.result === "Aprovado" ? "aprovado" : (s.result === "Reprovado" ? "reprovado" : "");
            cells += `<td class="${res_cls}">${frappe.utils.escape_html(s.result || "")}</td>`;

            return `<tr>${cells}</tr>`;
        }).join("");

        return `
            <table class="pf-table">
                <thead>
                    <tr>${th1}</tr>
                    <tr>${th2}</tr>
                    <tr>${th3}</tr>
                </thead>
                <tbody>${rows_html}</tbody>
            </table>
        `;
    }

    // -----------------------------------------------------------------------
    // Statistics table
    // -----------------------------------------------------------------------

    _build_stats_html(d) {
        const subjects = d.subjects;
        const terms    = d.terms;
        const n        = terms.length;
        const RANGES   = [[0, 4.4], [4.5, 9.4], [9.5, 13.4], [13.5, 17.4], [17.5, 20]];
        const RANGE_LABELS = ["00.0 – 04.4", "04.5 – 09.4", "09.5 – 13.4", "13.5 – 17.4", "17.5 – 20.0"];
        const min_pass = d.min_passing || 10;

        // Compute per-subject stats across all students and terms
        // For each subject, collect: list of MTs per student (using annual avg per subject)
        const subj_stats = subjects.map(subj => {
            const all_mf   = d.students.filter(s => s.annual_subject_avgs[subj.name] !== null && s.annual_subject_avgs[subj.name] !== undefined);
            const all_f    = all_mf.filter(s => s.gender === "Feminino" || s.gender === "F");

            const vals_mf  = all_mf.map(s => s.annual_subject_avgs[subj.name]);
            const vals_f   = all_f.map(s => s.annual_subject_avgs[subj.name]);

            const pos_mf   = vals_mf.filter(v => v >= min_pass);
            const pos_f    = vals_f.filter(v => v >= min_pass);

            const avg_mf   = vals_mf.length ? (vals_mf.reduce((a, b) => a + b, 0) / vals_mf.length) : null;

            const dist_mf  = RANGES.map(([lo, hi]) => vals_mf.filter(v => v >= lo && v <= hi).length);
            const dist_f   = RANGES.map(([lo, hi]) => vals_f.filter(v => v >= lo && v <= hi).length);

            return {
                label:   subj.subject_code || subj.subject_name,
                n_mf:    all_mf.length,
                n_f:     all_f.length,
                pos_mf:  pos_mf.length,
                pos_f:   pos_f.length,
                pct_mf:  all_mf.length ? Math.round(pos_mf.length * 100 / all_mf.length) : 0,
                pct_f:   all_f.length  ? Math.round(pos_f.length  * 100 / all_f.length)  : 0,
                avg:     avg_mf !== null ? String(Math.round(avg_mf)) : "",
                dist_mf,
                dist_f,
            };
        });

        // Also add portame column (comportamento — qualitative, skip distribution)
        const n_cols = subjects.length;

        // Header
        const subj_headers = subj_stats.map(ss =>
            `<th colspan="2">${frappe.utils.escape_html(ss.label)}</th>`
        ).join("");

        const _row = (label, vals) => {
            const cells = vals.map(v => `<td>${v !== null && v !== undefined ? v : ""}</td>`).join("");
            return `<tr><td class="label-cell">${label}</td>${cells}</tr>`;
        };

        // Build stats rows
        const n_avaliados_mf = _row("Nº Avaliados (MF)", subj_stats.map(s => s.n_mf));
        const n_avaliados_f  = _row("Nº Avaliados (F)",  subj_stats.map(s => s.n_f));
        const pos_mf         = _row("Sit. Positiva (MF)", subj_stats.map(s => s.pos_mf));
        const pos_f          = _row("Sit. Positiva (F)",  subj_stats.map(s => s.pos_f));
        const pct_mf         = _row("% Positiva (MF)",   subj_stats.map(s => s.pct_mf + "%"));
        const pct_f          = _row("% Positiva (F)",    subj_stats.map(s => s.pct_f + "%"));
        const avg_row        = _row("Nota Média",         subj_stats.map(s => s.avg));

        const dist_rows = RANGE_LABELS.map((lbl, ri) =>
            _row(lbl + " (MF)", subj_stats.map(s => s.dist_mf[ri] || 0)) +
            _row(lbl + " (F)",  subj_stats.map(s => s.dist_f[ri]  || 0))
        ).join("");

        // Final averages per discipline (global avg of annual_subject_avgs across all students)
        const final_avgs = subjects.map(subj => {
            const vals = d.students
                .map(s => s.annual_subject_avgs[subj.name])
                .filter(v => v !== null && v !== undefined);
            return vals.length ? String(Math.round(vals.reduce((a, b) => a + b, 0) / vals.length)) : "";
        });
        const final_avgs_row = _row("Média Final por Disciplina", final_avgs);

        return `
            <div style="font-size:11px;font-weight:700;color:#374151;margin-bottom:6px;">
                Estatísticas por Disciplina (Média Anual)
            </div>
            <table class="pf-stats-table">
                <thead>
                    <tr>
                        <th style="min-width:140px;text-align:left;">Indicador</th>
                        ${subj_headers}
                    </tr>
                </thead>
                <tbody>
                    ${n_avaliados_mf}${n_avaliados_f}
                    ${pos_mf}${pos_f}${pct_mf}${pct_f}
                    ${avg_row}
                    ${dist_rows}
                    ${final_avgs_row}
                </tbody>
            </table>
        `;
    }

    // -----------------------------------------------------------------------
    // Print
    // -----------------------------------------------------------------------

    _print() {
        if (!this.data) return;
        const html = this._build_print_html(this.data);
        const w = window.open("", "_blank");
        w.document.write(html);
        w.document.close();
        w.onload = () => w.print();
    }

    _build_print_html(d) {
        const subjects = d.subjects;
        const terms    = d.terms;
        const n        = terms.length;
        const RANGES   = [[0, 4.4], [4.5, 9.4], [9.5, 13.4], [13.5, 17.4], [17.5, 20]];
        const RANGE_LABELS = ["00.0 – 04.4", "04.5 – 09.4", "09.5 – 13.4", "13.5 – 17.4", "17.5 – 20.0"];
        const min_pass = d.min_passing || 10;

        const esc = (v) => frappe.utils.escape_html(String(v || ""));
        const fv  = (v) => { const n = parseFloat(v); return (!isNaN(n) && v !== null && v !== undefined) ? String(Math.round(n)) : ""; };
        const iv  = (v) => (v !== null && v !== undefined && v !== 0) ? v : "";

        // ---- Main table header row 1 ----
        let th1 = `<th rowspan="3">#</th>
                   <th rowspan="3" style="min-width:80px;max-width:100px;">Nome</th>
                   <th rowspan="3">G</th>`;
        subjects.forEach(s => {
            const cols = n * 3;
            th1 += `<th colspan="${cols}">${esc(s.subject_code || s.subject_name)}</th>`;
        });
        th1 += `<th colspan="${n}">PORT</th>`;
        th1 += `<th colspan="${subjects.length + 1}">MÉDIAS ANUAIS</th>`;
        th1 += `<th rowspan="3">RES.</th>`;

        // ---- row 2 ----
        let th2 = "";
        subjects.forEach(() => {
            th2 += `<th colspan="${n}">N</th><th colspan="${n}">F</th><th colspan="${n}">J</th>`;
        });
        th2 += `<th colspan="${n}"></th>`;
        subjects.forEach(s => {
            th2 += `<th>${esc(s.subject_code || s.subject_name)}</th>`;
        });
        th2 += `<th>MG</th>`;

        // ---- row 3 ----
        let th3 = "";
        subjects.forEach(() => {
            for (let g = 0; g < 3; g++) {
                terms.forEach((t, ti) => { th3 += `<th>${ti + 1}</th>`; });
            }
        });
        terms.forEach((t, ti) => { th3 += `<th>${ti + 1}</th>`; });
        subjects.forEach(() => th3 += `<th></th>`);
        th3 += `<th></th>`;

        // ---- student rows ----
        const student_rows = d.students.map(s => {
            let cells = `<td>${s.idx}</td>
                         <td style="text-align:left;font-size:6.5px;">${esc(s.student_name)}</td>
                         <td>${esc(s.gender ? s.gender[0] : "")}</td>`;

            subjects.forEach(subj => {
                for (let p = 1; p <= n; p++) {
                    cells += `<td>${fv(s.grades[subj.name] && s.grades[subj.name][p])}</td>`;
                }
                for (let p = 1; p <= n; p++) {
                    const abs = s.absences[p];
                    cells += `<td>${iv(abs && abs.unjustified)}</td>`;
                }
                for (let p = 1; p <= n; p++) {
                    const abs = s.absences[p];
                    cells += `<td>${iv(abs && abs.justified)}</td>`;
                }
            });

            for (let p = 1; p <= n; p++) {
                cells += `<td>${esc(_abbr_comp(s.comportamento[p] || ""))}</td>`;
            }

            subjects.forEach(subj => {
                cells += `<td style="background:#EFF6FF;font-weight:700;">${fv(s.annual_subject_avgs[subj.name])}</td>`;
            });
            cells += `<td style="background:#DBEAFE;font-weight:700;">${fv(s.global_average)}</td>`;

            const result_color = s.result === "Aprovado" ? "#059669" : (s.result === "Reprovado" ? "#DC2626" : "inherit");
            cells += `<td style="font-weight:700;color:${result_color};">${esc(s.result)}</td>`;

            return `<tr>${cells}</tr>`;
        }).join("");

        // ---- statistics section ----
        const subj_stats = subjects.map(subj => {
            const all_mf  = d.students.filter(s => s.annual_subject_avgs[subj.name] !== null && s.annual_subject_avgs[subj.name] !== undefined);
            const all_f   = all_mf.filter(s => s.gender === "Feminino" || s.gender === "F");
            const vals_mf = all_mf.map(s => s.annual_subject_avgs[subj.name]);
            const vals_f  = all_f.map(s => s.annual_subject_avgs[subj.name]);
            const pos_mf  = vals_mf.filter(v => v >= min_pass);
            const pos_f   = vals_f.filter(v => v >= min_pass);
            const avg_mf  = vals_mf.length ? (vals_mf.reduce((a, b) => a + b, 0) / vals_mf.length) : null;
            return {
                label:   subj.subject_code || subj.subject_name,
                n_mf: all_mf.length, n_f: all_f.length,
                pos_mf: pos_mf.length, pos_f: pos_f.length,
                pct_mf: all_mf.length ? Math.round(pos_mf.length * 100 / all_mf.length) : 0,
                pct_f:  all_f.length  ? Math.round(pos_f.length  * 100 / all_f.length)  : 0,
                avg: avg_mf !== null ? String(Math.round(avg_mf)) : "",
                dist_mf: RANGES.map(([lo, hi]) => vals_mf.filter(v => v >= lo && v <= hi).length),
                dist_f:  RANGES.map(([lo, hi]) => vals_f.filter(v => v >= lo && v <= hi).length),
            };
        });

        const stats_subj_headers = subj_stats.map(ss =>
            `<th colspan="2" style="background:#374151;color:#fff;">${esc(ss.label)}</th>`
        ).join("");

        const _sr = (label, vals) => {
            const cells = vals.map((v, i) => {
                const bg = i % 2 === 0 ? "" : "background:#F9FAFB;";
                return `<td style="${bg}">${v !== null && v !== undefined ? v : ""}</td><td style="${bg}"></td>`;
            }).join("");
            return `<tr><td style="text-align:left;font-weight:600;background:#F9FAFB;">${label}</td>${cells}</tr>`;
        };

        // Simplified stats rows for print
        const stat_rows = [
            _sr("Nº de alunos avaliados (MF)", subj_stats.map(s => s.n_mf)),
            _sr("Nº de alunos avaliados (F)",  subj_stats.map(s => s.n_f)),
            _sr("Alunos em sit. positiva (MF)", subj_stats.map(s => s.pos_mf)),
            _sr("Alunos em sit. positiva (F)",  subj_stats.map(s => s.pos_f)),
            _sr("% em situação positiva (MF)",  subj_stats.map(s => s.pct_mf + "%")),
            _sr("Nota média",                   subj_stats.map(s => s.avg)),
            ...RANGE_LABELS.map((lbl, ri) =>
                _sr(lbl + " (MF)", subj_stats.map(s => s.dist_mf[ri] || 0)) +
                _sr(lbl + " (F)",  subj_stats.map(s => s.dist_f[ri]  || 0))
            ),
        ].join("");

        // Médias finais
        const final_avgs = subjects.map(subj => {
            const vals = d.students.map(s => s.annual_subject_avgs[subj.name]).filter(v => v !== null && v !== undefined);
            return vals.length ? String(Math.round(vals.reduce((a, b) => a + b, 0) / vals.length)) : "";
        });
        const final_row = _sr("Média Final por Disciplina", final_avgs);

        return `<!DOCTYPE html>
<html lang="pt">
<head>
<meta charset="UTF-8">
<title>Pauta de Frequência — ${esc(d.class_group_name)} — ${esc(d.academic_year)}</title>
<style>
  @page { size: A3 landscape; margin: 8mm; }
  * { box-sizing: border-box; }
  body { font-family: Arial, sans-serif; font-size: 7px; color: #000; }
  .header { text-align: center; margin-bottom: 6px; }
  .header h2 { font-size: 10px; margin: 0; }
  .header h3 { font-size: 8px; margin: 2px 0 0; font-weight: normal; }
  .meta { display: flex; justify-content: center; gap: 24px; margin-bottom: 4px; font-size: 7px; font-weight: 700; }
  table { border-collapse: collapse; width: 100%; }
  th, td { border: 1px solid #888; padding: 2px 2px; text-align: center; white-space: nowrap; }
  th { background: #2D3748; color: #fff; font-size: 6.5px; font-weight: 700; }
  .subj-th { background: #1A3A5C; }
  .faltas-th { background: #4A5568; }
  .annual-th { background: #14532D; }
  .portame-th { background: #3730A3; }
  .stats-th { background: #374151; }
  td.name-cell { text-align: left; max-width: 90px; overflow: hidden; text-overflow: ellipsis; }
  td.avg-cell { background: #EFF6FF; font-weight: 700; }
  td.global-avg { background: #DBEAFE; font-weight: 700; }
  tr:nth-child(even) td { background: #F8FAFC; }
  tr:nth-child(even) td.avg-cell { background: #DBEAFE; }
  tr:nth-child(even) td.global-avg { background: #BFDBFE; }
  .aprovado { color: #059669; font-weight: 700; }
  .reprovado { color: #DC2626; font-weight: 700; }
  .stats-section { margin-top: 12px; page-break-inside: avoid; }
  .sig-section { margin-top: 16px; display: flex; justify-content: space-between; font-size: 7px; }
  .sig-box { flex: 1; border-top: 1px solid #000; padding-top: 4px; margin: 0 12px; text-align: center; }
</style>
</head>
<body>
  <div class="header">
    <h2>${esc(d.school_name)}</h2>
    <h3>PAUTA DE FREQUÊNCIA</h3>
  </div>
  <div class="meta">
    <span>TURMA: ${esc(d.class_group_name)}</span>
    ${d.school_class ? `<span>CLASSE: ${esc(d.school_class)}</span>` : ""}
    ${d.classroom ? `<span>SALA: ${esc(d.classroom)}</span>` : ""}
    ${d.shift ? `<span>TURNO: ${esc(d.shift)}</span>` : ""}
    <span>ANO LECTIVO: ${esc(d.academic_year)}</span>
  </div>

  <table>
    <thead>
      <tr>
        ${th1}
      </tr>
      <tr>${th2}</tr>
      <tr>${th3}</tr>
    </thead>
    <tbody>
      ${student_rows}
    </tbody>
  </table>

  <div class="stats-section">
    <table>
      <thead>
        <tr>
          <th style="min-width:110px;text-align:left;background:#374151;">Indicador</th>
          ${stats_subj_headers}
        </tr>
      </thead>
      <tbody>
        ${stat_rows}
        ${final_row}
      </tbody>
    </table>
  </div>

  <div class="sig-section">
    <div class="sig-box">Assinatura dos Professores</div>
    <div class="sig-box">Director Adjunto</div>
    <div class="sig-box">
      Homologação &mdash; A Directora<br>
      ___________________<br>
      …/…/……
    </div>
    <div class="sig-box">Assinatura do Secretário</div>
  </div>

  <script>
    window.onafterprint = function() { window.close(); };
  </script>
</body>
</html>`;
    }
}

// ---------------------------------------------------------------------------
// Helper: abbreviate comportamento label
// ---------------------------------------------------------------------------

function _abbr_comp(label) {
    if (!label) return "";
    const map = {
        "Muito Bom": "MB", "Bom": "B", "Satisfatório": "S", "Suficiente": "SF",
        "Insatisfatório": "I", "Mau": "M", "Muito Mau": "MM",
    };
    return map[label] || label.substring(0, 2).toUpperCase();
}
