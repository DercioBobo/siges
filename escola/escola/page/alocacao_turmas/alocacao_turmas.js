frappe.pages["alocacao-turmas"].on_page_load = function (wrapper) {
    const page = frappe.ui.make_app_page({
        parent: wrapper,
        title: __("Alocação de Turmas"),
        single_column: true,
    });
    wrapper._aloc = new AlocacaoTurmas(page, wrapper);
};

frappe.pages["alocacao-turmas"].on_page_show = function (wrapper) {
    const a = wrapper._aloc;
    if (!a) return;
    if (frappe.route_options) {
        const { academic_year, school_class } = frappe.route_options;
        frappe.route_options = null;
        a._pending_route = { academic_year, school_class };
        a._apply_route();
    } else if (a.data) {
        a._load();
    }
};

const ALOC_METHOD = "escola.escola.page.alocacao_turmas.alocacao_turmas.";

class AlocacaoTurmas {
    constructor(page, wrapper) {
        this.page = page;
        this.wrapper = wrapper;
        this.data = null;
        this.selected = {};   // school_class → Set(student)

        this._inject_styles();
        this._build_skeleton();
        this.page.add_button(__("Actualizar"), () => this._load(), { icon: "fa fa-refresh" });
        this._load_filter_options();
    }

    // -----------------------------------------------------------------------
    // Setup
    // -----------------------------------------------------------------------

    _inject_styles() {
        if (document.getElementById("aloc-styles")) return;
        const s = document.createElement("style");
        s.id = "aloc-styles";
        s.textContent = `
            .aloc-summary { display:flex;gap:12px;flex-wrap:wrap;margin-bottom:18px; }
            .aloc-stat { border:1px solid var(--border-color);border-radius:8px;padding:10px 16px;background:var(--card-bg);min-width:150px; }
            .aloc-stat-val { font-size:22px;font-weight:700; }
            .aloc-stat-lbl { font-size:12px;color:var(--text-muted); }
            .aloc-section { border:1px solid var(--border-color);border-radius:10px;margin-bottom:20px;background:var(--card-bg);overflow:hidden; }
            .aloc-section-head { display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap;
                                 padding:12px 16px;border-bottom:1px solid var(--border-color);background:var(--subtle-fg); }
            .aloc-section-title { font-size:15px;font-weight:700; }
            .aloc-badge { display:inline-block;font-size:11px;font-weight:600;padding:2px 8px;border-radius:10px;margin-left:8px; }
            .aloc-badge.warn { background:var(--yellow-highlight-color, #fef9c3);color:#854d0e; }
            .aloc-badge.ok { background:var(--green-highlight-color, #dcfce7);color:#166534; }
            .aloc-section-body { display:grid;grid-template-columns:minmax(260px,1fr) minmax(260px,1.3fr);gap:0; }
            @media (max-width: 900px) { .aloc-section-body { grid-template-columns:1fr; } }
            .aloc-col { padding:12px 16px; }
            .aloc-col + .aloc-col { border-left:1px solid var(--border-color); }
            @media (max-width: 900px) { .aloc-col + .aloc-col { border-left:none;border-top:1px solid var(--border-color); } }
            .aloc-col-title { font-size:11px;font-weight:700;letter-spacing:.5px;color:var(--text-muted);margin-bottom:8px;
                              display:flex;justify-content:space-between;align-items:center; }
            .aloc-search { width:100%;margin-bottom:8px; }
            .aloc-list { max-height:360px;overflow-y:auto;border:1px solid var(--border-color);border-radius:6px; }
            .aloc-row { display:flex;align-items:center;gap:10px;padding:7px 10px;border-bottom:1px solid var(--border-color);cursor:pointer; }
            .aloc-row:last-child { border-bottom:none; }
            .aloc-row:hover { background:var(--subtle-fg); }
            .aloc-row.checked { background:var(--primary-light, #eef2ff); }
            .aloc-row input { margin:0; }
            .aloc-row-name { flex:1;font-size:13px; }
            .aloc-row-meta { font-size:11px;color:var(--text-muted); }
            .aloc-turmas { display:flex;flex-direction:column;gap:10px; }
            .aloc-turma { border:1px solid var(--border-color);border-radius:8px;padding:10px 12px; }
            .aloc-turma.full { opacity:.6; }
            .aloc-turma-top { display:flex;justify-content:space-between;align-items:center;gap:8px; }
            .aloc-turma-name { font-weight:600;font-size:14px; }
            .aloc-turma-meta { font-size:11px;color:var(--text-muted); }
            .aloc-bar { height:6px;border-radius:3px;background:var(--border-color);margin-top:8px;overflow:hidden; }
            .aloc-bar > div { height:100%;border-radius:3px; }
            .aloc-empty { text-align:center;padding:24px 10px;color:var(--text-muted);font-size:13px; }
            .aloc-section-actions { display:flex;gap:8px;flex-wrap:wrap; }
        `;
        document.head.appendChild(s);
    }

    _build_skeleton() {
        const $body = $(this.wrapper).find(".page-content");
        $body.empty();
        this.$root = $(`
            <div style="padding:0 20px 60px;">
                <div class="aloc-filters"></div>
                <div class="aloc-body"></div>
            </div>
        `).appendTo($body);
        this.$filters = this.$root.find(".aloc-filters");
        this.$body = this.$root.find(".aloc-body");
    }

    // -----------------------------------------------------------------------
    // Filters
    // -----------------------------------------------------------------------

    _load_filter_options() {
        frappe.call({
            method: ALOC_METHOD + "get_filter_options",
            callback: (r) => {
                if (r.message) this._render_filters(r.message);
            },
        });
    }

    _render_filters({ years, classes, default_year }) {
        this.$filters.html(`
            <div style="display:flex;gap:16px;align-items:flex-end;flex-wrap:wrap;padding:18px 0 12px;">
                <div style="min-width:180px;" id="aloc-ctrl-year"></div>
                <div style="min-width:220px;" id="aloc-ctrl-class"></div>
            </div>`);

        this._year_ctrl = escola.utils.make_filter_select(
            this.$filters.find("#aloc-ctrl-year")[0],
            { label: __("ANO LECTIVO"), placeholder: __("Selecionar ano…"),
              options: years.map(y => ({ value: y.name, label: y.year_name || y.name })) }
        );
        this._class_ctrl = escola.utils.make_filter_select(
            this.$filters.find("#aloc-ctrl-class")[0],
            { label: __("CLASSE"), placeholder: __("Todas as classes"),
              options: classes.map(c => ({ value: c.name, label: c.class_name || c.name })) }
        );
        this._year_ctrl.on_change(() => this._load());
        this._class_ctrl.on_change(() => this._load());

        if (this._pending_route) {
            this._apply_route();
        } else {
            if (default_year) this._year_ctrl.set_value(default_year);
            this._load();
        }
    }

    _apply_route() {
        if (!this._year_ctrl || !this._pending_route) return;
        const { academic_year, school_class } = this._pending_route;
        this._pending_route = null;
        if (academic_year) this._year_ctrl.set_value(academic_year);
        this._class_ctrl.set_value(school_class || "");
        this._load();
    }

    // -----------------------------------------------------------------------
    // Data
    // -----------------------------------------------------------------------

    _load() {
        const year = this._year_ctrl && this._year_ctrl.get_value();
        if (!year) {
            this.$body.html(this._empty("fa-calendar", __("Seleccione o Ano Lectivo.")));
            return;
        }
        this.$body.html(`
            <div style="text-align:center;padding:60px;color:var(--text-muted);">
                <i class="fa fa-spinner fa-spin fa-2x"></i>
            </div>`);

        frappe.call({
            method: ALOC_METHOD + "get_allocation_data",
            args: { academic_year: year, school_class: this._class_ctrl.get_value() || null },
            callback: (r) => {
                if (r.exc) { this.$body.empty(); return; }
                this.data = r.message;
                this._prune_selection();
                this._render();
            },
        });
    }

    _prune_selection() {
        const next = {};
        (this.data.sections || []).forEach(sec => {
            const ids = new Set(sec.pending.map(p => p.student));
            const prev = this.selected[sec.school_class] || new Set();
            next[sec.school_class] = new Set([...prev].filter(s => ids.has(s)));
        });
        this.selected = next;
    }

    // -----------------------------------------------------------------------
    // Render
    // -----------------------------------------------------------------------

    _render() {
        const d = this.data;
        const sections = d.sections || [];
        const esc = frappe.utils.escape_html;

        const turmas_total = sections.reduce((n, s) => n + s.turmas.length, 0);
        const summary = `
            <div class="aloc-summary">
                <div class="aloc-stat">
                    <div class="aloc-stat-val" style="color:${d.total_pending ? "var(--orange-600, #c2410c)" : "var(--green-600, #16a34a)"};">${d.total_pending}</div>
                    <div class="aloc-stat-lbl">${__("Alunos por alocar")}</div>
                </div>
                <div class="aloc-stat">
                    <div class="aloc-stat-val">${sections.length}</div>
                    <div class="aloc-stat-lbl">${__("Classes")}</div>
                </div>
                <div class="aloc-stat">
                    <div class="aloc-stat-val">${turmas_total}</div>
                    <div class="aloc-stat-lbl">${__("Turmas activas")}</div>
                </div>
            </div>`;

        if (!sections.length) {
            this.$body.html(summary + this._empty("fa-check-circle",
                __("Não há alunos por alocar em {0}.", [esc(d.academic_year)])));
            return;
        }

        this.$body.html(summary + sections.map(sec => this._section_html(sec)).join(""));
        this._bind();
    }

    _section_html(sec) {
        const esc = frappe.utils.escape_html;
        const n = sec.pending.length;
        const badge = n
            ? `<span class="aloc-badge warn">${__("{0} por alocar", [n])}</span>`
            : `<span class="aloc-badge ok">${__("Todos alocados")}</span>`;

        const pending_html = n
            ? `<input type="text" class="form-control input-xs aloc-search" placeholder="${__("Pesquisar aluno…")}">
               <div class="aloc-list">${sec.pending.map(p => this._student_row(sec, p)).join("")}</div>`
            : this._empty("fa-check", __("Nenhum aluno pendente nesta classe."));

        const turmas_html = sec.turmas.length
            ? `<div class="aloc-turmas">${sec.turmas.map(t => this._turma_html(sec, t)).join("")}</div>`
            : this._empty("fa-users", __("Ainda não existem turmas para esta classe. Crie uma Nova Turma."));

        return `
            <div class="aloc-section" data-class="${esc(sec.school_class)}">
                <div class="aloc-section-head">
                    <div><span class="aloc-section-title">${esc(sec.class_name)}</span>${badge}</div>
                    <div class="aloc-section-actions">
                        <button class="btn btn-default btn-xs aloc-new-turma">+ ${__("Nova Turma")}</button>
                        ${n && sec.turmas.length ? `<button class="btn btn-default btn-xs aloc-auto">
                            <i class="fa fa-magic"></i> ${__("Distribuir automaticamente")}</button>` : ""}
                    </div>
                </div>
                <div class="aloc-section-body">
                    <div class="aloc-col">
                        <div class="aloc-col-title">
                            <span>${__("ALUNOS SEM TURMA")}</span>
                            ${n ? `<label style="margin:0;font-weight:400;cursor:pointer;">
                                <input type="checkbox" class="aloc-select-all"> ${__("Todos")}</label>` : ""}
                        </div>
                        ${pending_html}
                    </div>
                    <div class="aloc-col">
                        <div class="aloc-col-title"><span>${__("TURMAS")}</span>
                            <span class="aloc-sel-count" style="font-weight:400;"></span></div>
                        ${turmas_html}
                    </div>
                </div>
            </div>`;
    }

    _student_row(sec, p) {
        const esc = frappe.utils.escape_html;
        const checked = (this.selected[sec.school_class] || new Set()).has(p.student);
        const meta = [p.gender, p.enrollment_type, p.enrollment_date && frappe.datetime.str_to_user(p.enrollment_date)]
            .filter(Boolean).map(esc).join(" · ");
        return `
            <div class="aloc-row${checked ? " checked" : ""}" data-student="${esc(p.student)}"
                 data-search="${esc((p.student_name || "").toLowerCase())}">
                <input type="checkbox" ${checked ? "checked" : ""}>
                <div class="aloc-row-name">${esc(p.student_name || "")}
                    <div class="aloc-row-meta">${meta}</div></div>
                <a class="aloc-open-insc text-muted" href="/app/inscricao/${encodeURIComponent(p.inscricao)}"
                   title="${__("Abrir Inscrição")}"><i class="fa fa-external-link"></i></a>
            </div>`;
    }

    _turma_html(sec, t) {
        const esc = frappe.utils.escape_html;
        const count = t.student_count || 0;
        const max = t.max_students || 0;
        const full = max > 0 && count >= max;
        const pct = max > 0 ? Math.min(100, Math.round(count / max * 100)) : 0;
        const color = full ? "var(--red-500, #ef4444)" : pct >= 90 ? "var(--yellow-500, #eab308)" : "var(--green-500, #22c55e)";
        const cap = max > 0
            ? __("{0} / {1} alunos · {2} vaga(s)", [count, max, Math.max(0, max - count)])
            : __("{0} alunos · sem limite", [count]);
        const meta = [t.shift, t.classroom && __("Sala {0}", [t.classroom])].filter(Boolean).map(esc).join(" · ");
        return `
            <div class="aloc-turma${full ? " full" : ""}" data-turma="${esc(t.name)}" data-free="${max > 0 ? max - count : -1}">
                <div class="aloc-turma-top">
                    <div>
                        <a class="aloc-turma-name" href="/app/class-group/${encodeURIComponent(t.name)}">${esc(t.group_name)}</a>
                        <div class="aloc-turma-meta">${cap}${meta ? " · " + meta : ""}</div>
                    </div>
                    ${full ? `<span class="aloc-badge" style="background:var(--red-highlight-color,#fee2e2);color:#991b1b;">${__("Lotada")}</span>`
                           : `<button class="btn btn-primary btn-xs aloc-assign" disabled>${__("Alocar aqui")}</button>`}
                </div>
                ${max > 0 ? `<div class="aloc-bar"><div style="width:${pct}%;background:${color};"></div></div>` : ""}
            </div>`;
    }

    _empty(icon, msg) {
        return `<div class="aloc-empty"><i class="fa ${icon}" style="font-size:20px;display:block;margin-bottom:6px;"></i>${msg}</div>`;
    }

    // -----------------------------------------------------------------------
    // Interaction
    // -----------------------------------------------------------------------

    _bind() {
        const me = this;
        this.$body.find(".aloc-section").each(function () {
            const $sec = $(this);
            const cls = $sec.data("class");
            const sec = me.data.sections.find(s => s.school_class === cls);
            if (!me.selected[cls]) me.selected[cls] = new Set();
            const sel = me.selected[cls];

            const refresh_state = () => {
                const n = sel.size;
                $sec.find(".aloc-sel-count").text(n ? __("{0} seleccionado(s)", [n]) : "");
                $sec.find(".aloc-turma").each(function () {
                    const free = parseInt($(this).data("free"), 10);
                    const $btn = $(this).find(".aloc-assign");
                    $btn.prop("disabled", !n || (free >= 0 && n > free));
                    $btn.attr("title", free >= 0 && n > free ? __("Apenas {0} vaga(s) disponível(is)", [free]) : "");
                    $btn.text(n ? __("Alocar {0} aqui", [n]) : __("Alocar aqui"));
                });
                const visible = $sec.find(".aloc-row:visible");
                $sec.find(".aloc-select-all").prop("checked",
                    visible.length > 0 && visible.toArray().every(el => sel.has($(el).data("student"))));
            };

            $sec.on("click", ".aloc-row", function (e) {
                if ($(e.target).closest(".aloc-open-insc").length) return;
                const student = $(this).data("student");
                const on = !sel.has(student);
                on ? sel.add(student) : sel.delete(student);
                $(this).toggleClass("checked", on).find("input").prop("checked", on);
                refresh_state();
            });

            $sec.on("change", ".aloc-select-all", function () {
                const on = $(this).prop("checked");
                $sec.find(".aloc-row:visible").each(function () {
                    const student = $(this).data("student");
                    on ? sel.add(student) : sel.delete(student);
                    $(this).toggleClass("checked", on).find("input").prop("checked", on);
                });
                refresh_state();
            });

            $sec.on("input", ".aloc-search", function () {
                const q = ($(this).val() || "").toLowerCase().trim();
                $sec.find(".aloc-row").each(function () {
                    $(this).toggle(!q || String($(this).data("search")).includes(q));
                });
                refresh_state();
            });

            $sec.on("click", ".aloc-assign", function () {
                me._assign($(this).closest(".aloc-turma").data("turma"), [...sel]);
            });

            $sec.on("click", ".aloc-new-turma", () => {
                escola.utils.new_turma_dialog({
                    academic_year: me.data.academic_year,
                    school_class: cls,
                    on_created: () => me._load(),
                });
            });

            $sec.on("click", ".aloc-auto", () => me._auto(sec));

            refresh_state();
        });
    }

    _assign(class_group, students) {
        if (!students.length) return;
        frappe.call({
            method: ALOC_METHOD + "allocate",
            args: { class_group, students },
            freeze: true,
            freeze_message: __("A alocar alunos…"),
            callback: (r) => {
                if (r.exc) return;
                this._report(r.message);
                this._load();
            },
        });
    }

    _auto(sec) {
        const academic_year = this.data.academic_year;
        frappe.call({
            method: ALOC_METHOD + "auto_allocate",
            args: { academic_year, school_class: sec.school_class, dry_run: 1 },
            callback: (r) => {
                if (r.exc) return;
                const { plan, leftover } = r.message;
                if (!plan.length) {
                    frappe.msgprint(__("Não há vagas disponíveis nas turmas desta classe. Crie uma Nova Turma."));
                    return;
                }
                const esc = frappe.utils.escape_html;
                const rows = plan.map(p => `<li><b>${esc(p.group_name)}</b>: ${__("{0} aluno(s)", [p.count])}</li>`).join("");
                const warn = leftover
                    ? `<p style="color:var(--red-600,#dc2626);">${__("{0} aluno(s) ficarão sem turma por falta de vagas.", [leftover])}</p>`
                    : "";
                frappe.confirm(
                    `<p>${__("Distribuição proposta para {0} (equilibrada por ocupação e género):", [esc(sec.class_name)])}</p>
                     <ul>${rows}</ul>${warn}`,
                    () => frappe.call({
                        method: ALOC_METHOD + "auto_allocate",
                        args: { academic_year, school_class: sec.school_class, dry_run: 0 },
                        freeze: true,
                        freeze_message: __("A distribuir alunos…"),
                        callback: (r2) => {
                            if (r2.exc) return;
                            this._report(r2.message);
                            this._load();
                        },
                    })
                );
            },
        });
    }

    _report({ created = 0, errors = [] }) {
        if (!errors.length) {
            frappe.show_alert({ message: __("{0} aluno(s) alocado(s).", [created]), indicator: "green" });
            return;
        }
        const esc = frappe.utils.escape_html;
        frappe.msgprint({
            title: __("Alocação parcial"),
            indicator: "orange",
            message: `<p>${__("{0} aluno(s) alocado(s). Não foi possível alocar:", [created])}</p>
                <ul>${errors.map(e => `<li><b>${esc(e.student)}</b>: ${e.error}</li>`).join("")}</ul>`,
        });
    }
}
