frappe.pages["mapa-aproveitamento"].on_page_load = function (wrapper) {
    const page = frappe.ui.make_app_page({
        parent: wrapper,
        title: __("Mapa de Aproveitamento"),
        single_column: true,
    });
    wrapper._mapa = new MapaAproveitamento(page, wrapper);
};

frappe.pages["mapa-aproveitamento"].on_page_show = function (wrapper) {
    if (!frappe.route_options || !wrapper._mapa) return;
    wrapper._mapa._preselect = frappe.route_options;
    frappe.route_options = null;
    wrapper._mapa._apply_preselect();
};

// ---------------------------------------------------------------------------

class MapaAproveitamento {
    constructor(page, wrapper) {
        this.page      = page;
        this.wrapper   = wrapper;
        this.data      = null;
        this.annual_data = null;
        this._view     = "trimestral";   // "trimestral" | "annual"
        this._idx      = 0;
        this._dirty    = new Set();
        this._att_active = false;         // is the Faltas & Comportamento tab showing?
        this._att_dirty  = false;         // unsaved changes in the attendance tab
        this._preselect = frappe.route_options || null;
        if (this._preselect) frappe.route_options = null;

        this._inject_styles();
        this._build_skeleton();
        this._load_filter_options();
    }

    // -----------------------------------------------------------------------
    // Setup
    // -----------------------------------------------------------------------

    _inject_styles() {
        if (document.getElementById("ma-styles")) return;
        const s = document.createElement("style");
        s.id = "ma-styles";
        s.textContent = `
            .ma-label { font-size:11px;color:#6B7280;font-weight:700;display:block;
                        margin-bottom:4px;letter-spacing:.5px; }
            .ma-tab-btn { display:inline-flex;align-items:center;gap:6px;padding:7px 14px;
                          border:1px solid #E5E7EB;border-radius:20px;cursor:pointer;
                          font-size:13px;font-weight:600;white-space:nowrap;background:white;
                          color:#374151;transition:all .12s;margin:0 4px 4px 0; }
            .ma-tab-btn:hover { border-color:#6366F1;color:#6366F1; }
            .ma-tab-btn.active { background:#6366F1;color:white;border-color:#6366F1; }
            .ma-tab-btn.dirty { border-style:dashed; }
            .ma-view-btn.active { background:#0F172A;border-color:#0F172A; }
            .ma-dot { width:9px;height:9px;border-radius:50%;display:inline-block;flex-shrink:0; }
            .ma-score { width:46px;padding:3px 4px;text-align:center;
                        border:1px solid #E5E7EB;border-radius:4px;font-size:13px; }
            .ma-score:focus { outline:none;border-color:#6366F1;box-shadow:0 0 0 2px #6366F11A; }
            .ma-score:disabled { background:#F3F4F6;color:#D1D5DB; }
            .ma-att-comp { padding:3px 4px;border:1px solid #E5E7EB;border-radius:4px;
                           font-size:12px;max-width:150px;background:white;color:#374151; }
            .ma-att-comp:focus { outline:none;border-color:#6366F1;box-shadow:0 0 0 2px #6366F11A; }
            .ma-att-comp:disabled { background:#F3F4F6;color:#9CA3AF; }
            .ma-risk-badge { color:#DC2626;font-size:14px;font-weight:700; }
            .ma-grid { width:100%;border-collapse:collapse; }
            .ma-grid th { background:#1E293B;color:white;padding:8px 6px;font-size:11px;
                          font-weight:700;text-align:center;white-space:nowrap; }
            .ma-grid th.left { text-align:left; }
            .ma-grid td { padding:5px 4px;text-align:center;
                          border-bottom:1px solid #F3F4F6;vertical-align:middle; }
            .ma-grid td.left { text-align:left;font-size:12px;max-width:170px;
                               overflow:hidden;text-overflow:ellipsis;white-space:nowrap; }
            .ma-grid td.computed { font-size:12px;font-weight:700;background:#F9FAFB;color:#374151; }
            .ma-grid td.mt-cell { color:#6366F1;font-weight:800; }
            .ma-grid td.mt-cell.pos { color:#047857;background:#ECFDF5; }
            .ma-grid td.mt-cell.neg { color:#DC2626;background:#FEF2F2; }
            .ma-grid tr:hover td { background:#F0F4FF; }
            .ma-grid tr:hover td.computed { background:#E8EDFF; }
            .ma-grid tr:hover td.mt-cell.pos { background:#D1FAE5; }
            .ma-grid tr:hover td.mt-cell.neg { background:#FEE2E2; }
            .ma-kpi { display:flex;align-items:center;gap:10px;background:white;
                      border:1px solid #E5E7EB;border-radius:10px;padding:9px 15px;
                      box-shadow:0 1px 2px rgba(16,24,40,.04); }
            .ma-kpi-ic { width:30px;height:30px;border-radius:8px;display:flex;
                         align-items:center;justify-content:center;font-size:14px;flex-shrink:0; }
            .ma-kpi-val { font-size:18px;font-weight:800;line-height:1.05;color:#111827; }
            .ma-kpi-lbl { font-size:10px;font-weight:700;color:#9CA3AF;text-transform:uppercase;
                          letter-spacing:.4px;margin-top:3px; }
            .ma-annual-term-sep { border-left:2px solid #E5E7EB !important; }
            @media print {
                .ma-filters,.ma-tabs,.ma-toolbar,.navbar,.page-head,.page-actions,
                .layout-side-section { display:none !important; }
            }
        `;
        document.head.appendChild(s);
    }

    _build_skeleton() {
        const $body = $(this.wrapper).find(".page-content");
        $body.empty();
        this.$root = $(`
            <div style="padding:0 20px 60px;">
                <div class="ma-filters" style="padding:18px 0 12px;"></div>
                <div class="ma-tabs" style="margin-bottom:14px;"></div>
                <div class="ma-grid-area"></div>
            </div>
        `).appendTo($body);
        this.$filters   = this.$root.find(".ma-filters");
        this.$tabs      = this.$root.find(".ma-tabs");
        this.$grid_area = this.$root.find(".ma-grid-area");
    }

    // -----------------------------------------------------------------------
    // Filters
    // -----------------------------------------------------------------------

    _load_filter_options() {
        frappe.call({
            method: "escola.escola.page.mapa_aproveitamento.mapa_aproveitamento.get_filter_options",
            callback: (r) => {
                if (!r.message) return;
                this._render_filters(r.message);
            },
        });
    }

    _render_filters({ class_groups, terms }) {
        this._cg_year_map = {};
        class_groups.forEach(c => { this._cg_year_map[c.name] = c.academic_year; });
        this._all_terms = terms;

        this.$filters.html(`
            <div style="display:flex;gap:16px;align-items:flex-end;flex-wrap:wrap;padding:18px 0 12px;">
                <div style="min-width:220px;" id="ma-ctrl-cg"></div>
                <div style="min-width:220px;" id="ma-ctrl-term" class="ma-term-area"></div>
                <div id="ma-view-toggle" style="padding-bottom:2px;">
                    <span class="ma-label">VISTA</span>
                    <div style="display:flex;gap:4px;">
                        <button class="ma-tab-btn ma-view-btn active" data-view="trimestral">Por Trimestre</button>
                        <button class="ma-tab-btn ma-view-btn" data-view="annual">Anual</button>
                    </div>
                </div>
            </div>`);

        this._cg_ctrl = escola.utils.make_filter_select(
            this.$filters.find("#ma-ctrl-cg")[0],
            { label: __("TURMA"), placeholder: __("Pesquisar turma…"),
              options: class_groups.map(c => ({ value: c.name, label: c.group_name })) }
        );
        this._term_ctrl = escola.utils.make_filter_select(
            this.$filters.find("#ma-ctrl-term")[0],
            { label: __("PERÍODO"), placeholder: __("Selecionar período…"),
              options: terms.map(t => ({ value: t.name, label: `${t.term_name || t.name} (${t.academic_year})` })) }
        );

        this._cg_ctrl.on_change(cg => {
            this._populate_terms(cg);
            this._autoselect_term(cg);
        });
        this._term_ctrl.on_change(() => this._maybe_load());

        this.$filters.find(".ma-view-btn").on("click", (e) => {
            const view = $(e.currentTarget).data("view");
            this._switch_view(view);
        });

        this._apply_preselect();
    }

    _switch_view(view) {
        if (this._view === view) return;
        this._view = view;
        this.$filters.find(".ma-view-btn").each((_, btn) => {
            $(btn).toggleClass("active", $(btn).data("view") === view);
        });
        this.$filters.find(".ma-term-area").toggle(view === "trimestral");
        this._idx = 0;
        this._dirty.clear();
        this._att_dirty  = false;
        this._att_active = false;
        this.$tabs.empty();
        this.$grid_area.empty();
        this._maybe_load();
    }

    _apply_preselect() {
        if (!this._preselect) return;
        const { class_group, academic_term } = this._preselect;
        this._preselect = null;
        if (!class_group) return;
        this._cg_ctrl.set_value(class_group);
        this._populate_terms(class_group);
        if (academic_term) {
            this._term_ctrl.set_value(academic_term);
            this._maybe_load();
        } else {
            this._autoselect_term(class_group);
        }
    }

    /** Default PERÍODO to the current active term for the turma's year, then load. */
    _autoselect_term(cg) {
        if (this._view === "annual") { this._maybe_load(); return; }
        const year = this._cg_year_map && this._cg_year_map[cg];
        if (!year || this._term_ctrl.get_value()) { this._maybe_load(); return; }
        frappe.call({
            method: "escola.escola.doctype.grade_entry.grade_entry.get_current_academic_term",
            args: { academic_year: year },
            callback: (r) => {
                if (r.message) this._term_ctrl.set_value(r.message);
                this._maybe_load();
            },
        });
    }

    _populate_terms(cg) {
        const year = this._cg_year_map && this._cg_year_map[cg];
        const filtered = (this._all_terms || []).filter(t => !year || t.academic_year === year);
        this._term_ctrl.set_options(
            filtered.map(t => ({ value: t.name, label: `${t.term_name || t.name} (${t.academic_year})` }))
        );
    }

    _maybe_load() {
        if (this._view === "annual") {
            if (this._cg_ctrl.get_value()) this._load_annual();
        } else {
            if (this._cg_ctrl.get_value() && this._term_ctrl.get_value()) this._load();
        }
    }

    // -----------------------------------------------------------------------
    // Trimestral — data loading
    // -----------------------------------------------------------------------

    _load() {
        const cg   = this._cg_ctrl.get_value();
        const term = this._term_ctrl.get_value();
        if (!cg || !term) return;
        if (this._dirty.size > 0 || this._att_dirty) {
            frappe.confirm(
                __("Há alterações não guardadas. Carregar nova seleção sem guardar?"),
                () => this._do_load(cg, term)
            );
        } else {
            this._do_load(cg, term);
        }
    }

    _do_load(cg, term) {
        this._dirty.clear();
        this._att_dirty  = false;
        this._att_active = false;
        this._idx = 0;
        this.$tabs.empty();
        this.$grid_area.html(`
            <div style="text-align:center;padding:60px;color:#9CA3AF;">
                <i class="fa fa-spinner fa-spin fa-2x"></i>
                <div style="margin-top:12px;font-size:14px;">A carregar pauta…</div>
            </div>
        `);
        frappe.call({
            method: "escola.escola.page.mapa_aproveitamento.mapa_aproveitamento.get_grade_book",
            args: { class_group: cg, academic_term: term },
            callback: (r) => {
                if (r.exc) return;
                this.data = r.message;
                this._render();
            },
        });
    }

    // -----------------------------------------------------------------------
    // Annual — data loading
    // -----------------------------------------------------------------------

    _load_annual() {
        const cg = this._cg_ctrl.get_value();
        if (!cg) return;
        const year = this._cg_year_map && this._cg_year_map[cg];
        if (!year) return;
        this._do_load_annual(cg, year);
    }

    _do_load_annual(cg, year) {
        this._idx = 0;
        this._att_active = false;
        this.$tabs.empty();
        this.$grid_area.html(`
            <div style="text-align:center;padding:60px;color:#9CA3AF;">
                <i class="fa fa-spinner fa-spin fa-2x"></i>
                <div style="margin-top:12px;font-size:14px;">A carregar mapa anual…</div>
            </div>
        `);
        frappe.call({
            method: "escola.escola.page.mapa_aproveitamento.mapa_aproveitamento.get_annual_grade_book",
            args: { class_group: cg, academic_year: year },
            callback: (r) => {
                if (r.exc) return;
                this.annual_data = r.message;
                this._render_annual();
            },
        });
    }

    // -----------------------------------------------------------------------
    // Trimestral — render
    // -----------------------------------------------------------------------

    _render() {
        const d = this.data;
        if (!d) return;

        if (!d.subjects || !d.subjects.length) {
            this.$tabs.empty();
            this.$grid_area.html(this._empty_state(
                "fa-book",
                "Sem currículo activo",
                `A Turma <b>${frappe.utils.escape_html(d.class_group_name)}</b> não tem currículo activo com disciplinas.`
            ));
            return;
        }
        if (!d.students || !d.students.length) {
            this.$tabs.empty();
            this.$grid_area.html(this._empty_state(
                "fa-users",
                "Sem alunos activos",
                `Não existem alunos activos na Turma <b>${frappe.utils.escape_html(d.class_group_name)}</b>.`
            ));
            return;
        }

        this._render_tabs();
        this._show_subject(this._idx);
    }

    _empty_state(icon, title, msg) {
        return `
            <div style="text-align:center;padding:70px 20px;background:#F9FAFB;
                        border-radius:12px;border:1px dashed #E5E7EB;">
                <i class="fa ${icon} fa-3x" style="color:#D1D5DB;"></i>
                <h3 style="color:#374151;margin-top:16px;">${title}</h3>
                <p style="color:#6B7280;">${msg}</p>
            </div>`;
    }

    // -----------------------------------------------------------------------
    // Shared tabs
    // -----------------------------------------------------------------------

    _dot_color(status) {
        return { "Completo": "#10B981", "Em Curso": "#F59E0B", "Vazio": "#D1D5DB" }[status] || "#D1D5DB";
    }

    _render_tabs() {
        const d = this.data;
        let html = `<div style="display:flex;flex-wrap:wrap;">`;
        d.subjects.forEach((s, i) => {
            const active = (!this._att_active && i === this._idx) ? " active" : "";
            const dirty  = this._dirty.has(i) ? " dirty" : "";
            const lock   = (s.prev_locked && s.ge_docstatus !== 1)
                ? `<i class="fa fa-lock" style="color:#92400E;font-size:10px;"></i>` : "";
            html += `
                <button class="ma-tab-btn${active}${dirty}" data-idx="${i}">
                    <span class="ma-dot" style="background:${this._dot_color(s.status)};"></span>
                    ${lock}${frappe.utils.escape_html(s.subject_name)}
                </button>`;
        });
        // Class-level Faltas & Comportamento tab (independent of subject)
        const attActive = this._att_active ? " active" : "";
        const attDirty  = this._att_dirty ? " dirty" : "";
        html += `
            <button class="ma-tab-btn ma-att-tab${attActive}${attDirty}"
                    style="margin-left:10px;border-style:dashed;border-color:#CBD5E1;">
                <i class="fa fa-calendar-times-o"></i>&nbsp;${__("Faltas & Comportamento")}
            </button>`;
        html += `</div>`;
        this.$tabs.html(html);
        this.$tabs.find(".ma-tab-btn[data-idx]").on("click", (e) => {
            const idx = parseInt($(e.currentTarget).data("idx"));
            this._switch_subject(idx);
        });
        this.$tabs.find(".ma-att-tab").on("click", () => this._switch_to_att());
    }

    _switch_subject(idx) {
        if (!this._att_active && idx === this._idx) return;
        const leaving_dirty = this._att_active ? this._att_dirty : this._dirty.has(this._idx);
        if (leaving_dirty) {
            frappe.confirm(
                __("Há alterações não guardadas. Mudar sem guardar?"),
                () => {
                    if (this._att_active) this._att_dirty = false;
                    else this._dirty.delete(this._idx);
                    this._do_switch(idx);
                }
            );
        } else {
            this._do_switch(idx);
        }
    }

    _do_switch(idx) {
        this._att_active = false;
        this._idx = idx;
        this._render_tabs();
        this._show_subject(idx);
    }

    _switch_to_att() {
        if (this._att_active) return;
        if (this._dirty.has(this._idx)) {
            frappe.confirm(
                __("Há notas não guardadas nesta disciplina. Mudar sem guardar?"),
                () => {
                    this._dirty.delete(this._idx);
                    this._do_switch_att();
                }
            );
        } else {
            this._do_switch_att();
        }
    }

    _do_switch_att() {
        this._att_active = true;
        this._render_tabs();
        this._show_attendance();
    }

    // -----------------------------------------------------------------------
    // Trimestral — grid
    // -----------------------------------------------------------------------

    _show_subject(idx) {
        const d    = this.data;
        const subj = d.subjects[idx];
        if (!subj) return;

        const locked      = subj.ge_docstatus === 1;
        const prev_locked = !!subj.prev_locked && !locked;
        const read_only   = locked || prev_locked;

        const ge_link = subj.grade_entry
            ? `<a href="/app/grade-entry/${encodeURIComponent(subj.grade_entry)}" target="_blank"
                  style="font-size:11px;color:#6366F1;margin-left:10px;">
                   <i class="fa fa-external-link"></i> ${subj.grade_entry}
               </a>`
            : "";

        let actions;
        if (locked) {
            actions = `<span style="background:#dcfce7;color:#166534;border-radius:20px;
                            padding:4px 14px;font-size:12px;font-weight:700;">
                   <i class="fa fa-lock"></i>&nbsp;${__("Finalizada")}
               </span>`;
        } else if (prev_locked) {
            actions = `<span style="background:#FEF3C7;color:#92400E;border-radius:20px;
                            padding:4px 14px;font-size:12px;font-weight:600;">
                   <i class="fa fa-lock"></i>&nbsp;${__("Finalize a pauta do período anterior ({0}) primeiro",
                        [frappe.utils.escape_html(d.prev_term_name || "")])}
               </span>`;
        } else {
            actions = `<div style="display:flex;gap:8px;">
                   <button class="btn btn-default btn-sm ma-save-btn" data-idx="${idx}">
                       <i class="fa fa-floppy-o"></i>&nbsp;${__("Guardar")}
                   </button>
                   <button class="btn btn-primary btn-sm ma-finalizar-btn" data-idx="${idx}"
                           ${subj.grade_entry ? "" : "disabled title='Guarde primeiro'"}>
                       <i class="fa fa-check-circle"></i>&nbsp;${__("Finalizar")}
                   </button>
               </div>`;
        }

        const toolbar = `
            <div class="ma-toolbar" style="display:flex;align-items:center;
                                           justify-content:space-between;margin-bottom:10px;
                                           flex-wrap:wrap;gap:8px;">
                <div>
                    <span style="font-size:16px;font-weight:700;color:#1E293B;">
                        ${frappe.utils.escape_html(subj.subject_name)}
                    </span>
                    <span style="font-size:12px;color:#9CA3AF;margin-left:8px;">
                        ${frappe.utils.escape_html(d.term_name)} — ${frappe.utils.escape_html(d.class_group_name)}
                    </span>
                    ${ge_link}
                </div>
                ${actions}
            </div>
        `;

        this.$grid_area.html(toolbar + this._build_grid_html(subj, d.students));

        if (read_only) {
            this.$grid_area.find("input").prop("disabled", true).css("background", "var(--control-bg)");
        } else {
            this.$grid_area.find(".ma-save-btn").on("click", () => this._save(idx));
            this.$grid_area.find(".ma-finalizar-btn").on("click", () => this._finalizar(idx));
        }

        this._setup_grid_events(idx);
        this._update_footer(idx);
    }

    _build_grid_html(subj, students) {
        const row_map = {};
        (subj.rows || []).forEach(r => { row_map[r.student] = r; });

        const _v    = (v) => (v !== null && v !== undefined) ? v : "";
        const _f2   = (v) => { const n = parseFloat(v); return (!isNaN(n) && v !== null && v !== undefined) ? String(Math.round(n)) : ""; };

        const rows_html = students.map((s, i) => {
            const r   = row_map[s.student] || {};
            const abs = r.is_absent ? 1 : 0;
            const dis = abs ? " disabled" : "";

            const inp = (f) =>
                `<input type="number" class="ma-score" data-field="${f}"
                        min="0" max="20" step="1" value="${_v(r[f])}"${dis}>`;

            return `
                <tr data-student="${frappe.utils.escape_html(s.student)}">
                    <td style="color:#9CA3AF;font-size:11px;width:26px;">${i + 1}</td>
                    <td class="left" title="${frappe.utils.escape_html(s.student_name)}">
                        ${frappe.utils.escape_html(s.student_name)}
                    </td>
                    <td>${inp("acsp_1")}</td>
                    <td>${inp("acsp_2")}</td>
                    <td class="computed" data-field="macsp">${_f2(r.macsp)}</td>
                    <td>${inp("acse_1")}</td>
                    <td>${inp("acse_2")}</td>
                    <td class="computed" data-field="macs">${_f2(r.macs)}</td>
                    <td>${inp("acp")}</td>
                    <td class="computed mt-cell" data-field="mt">${_f2(r.mt)}</td>
                </tr>`;
        }).join("");

        return `
            <div style="overflow-x:auto;-webkit-overflow-scrolling:touch;">
            <table class="ma-grid">
                <thead>
                    <tr>
                        <th>#</th>
                        <th class="left" style="min-width:150px;">Nome</th>
                        <th title="Avaliação Contínua Sistemática Prática 1">ACSP 1</th>
                        <th title="Avaliação Contínua Sistemática Prática 2">ACSP 2</th>
                        <th title="Média das ACSP">MACSP</th>
                        <th title="Avaliação Contínua Sistemática Escrita 1">ACSE 1</th>
                        <th title="Avaliação Contínua Sistemática Escrita 2">ACSE 2</th>
                        <th title="Média das ACS">MACS</th>
                        <th title="Avaliação de Término Parcial">AT</th>
                        <th title="Média do Trimestre">MT</th>
                    </tr>
                </thead>
                <tbody>${rows_html}</tbody>
            </table>
            </div>
            <div class="ma-stats" style="display:flex;gap:20px;padding:10px 4px;
                                         flex-wrap:wrap;margin-top:6px;"></div>
        `;
    }

    _setup_grid_events(idx) {
        const $area = this.$grid_area;

        $area.find(".ma-score").on("input", (e) => {
            const $tr = $(e.target).closest("tr");
            this._recalc_row($tr);
            this._mark_dirty(idx);
            this._update_footer(idx);
        });

        // Tab/Shift+Tab between score inputs
        $area.find(".ma-score").on("keydown", (e) => {
            if (e.key !== "Tab") return;
            e.preventDefault();
            const $all = $area.find(".ma-score:not(:disabled)");
            const cur  = $all.index(e.target);
            $all.eq(cur + (e.shiftKey ? -1 : 1)).focus().select();
        });
    }

    _recalc_row($tr) {
        const _n  = (f) => { const v = parseFloat($tr.find(`[data-field="${f}"]`).val()); return isNaN(v) ? null : v; };
        const _ri = (v) => Math.round(v);

        const acsp = ["acsp_1","acsp_2"].map(_n).filter(v => v !== null);
        const macsp = acsp.length ? _ri(acsp.reduce((a,b)=>a+b,0)/acsp.length) : null;
        $tr.find("[data-field='macsp']").text(macsp !== null ? macsp : "");

        const acse = ["acse_1","acse_2"].map(_n).filter(v => v !== null);
        const macs_in = (macsp !== null ? [macsp] : []).concat(acse);
        const macs = macs_in.length ? _ri(macs_in.reduce((a,b)=>a+b,0)/macs_in.length) : null;
        $tr.find("[data-field='macs']").text(macs !== null ? macs : "");

        const acp = _n("acp");
        const mt  = (macs !== null && acp !== null) ? _ri((2*macs + acp)/3) : null;
        const $mt = $tr.find("[data-field='mt']");
        $mt.text(mt !== null ? mt : "").removeClass("pos neg");
        if (mt !== null) $mt.addClass(mt >= 10 ? "pos" : "neg");
    }

    _mark_dirty(idx) {
        if (!this._dirty.has(idx)) {
            this._dirty.add(idx);
            this.$tabs.find(`.ma-tab-btn[data-idx="${idx}"]`).addClass("dirty");
        }
    }

    _update_footer(idx) {
        const $stats = this.$grid_area.find(".ma-stats");
        if (!$stats.length) return;
        let approved = 0, failed = 0, no_data = 0, sum = 0, cnt = 0;
        // Single pass: recolour the MT cells and gather the class KPIs.
        this.$grid_area.find(".ma-grid tbody tr").each((_, tr) => {
            const $mt = $(tr).find("[data-field='mt']");
            const mt  = parseFloat($mt.text());
            $mt.removeClass("pos neg");
            if (!isNaN(mt)) {
                $mt.addClass(mt >= 10 ? "pos" : "neg");
                mt >= 10 ? approved++ : failed++;
                sum += mt; cnt++;
            } else {
                no_data++;
            }
        });
        const total = (this.data && this.data.students) ? this.data.students.length : 0;
        const avg   = cnt ? (sum / cnt).toFixed(1) : "—";
        const avg_color = !cnt ? "#9CA3AF" : (sum / cnt >= 10 ? "#047857" : "#DC2626");

        const kpi = (ic, ic_bg, ic_color, val, val_color, lbl) => `
            <div class="ma-kpi">
                <div class="ma-kpi-ic" style="background:${ic_bg};color:${ic_color};">
                    <i class="fa ${ic}"></i>
                </div>
                <div>
                    <div class="ma-kpi-val" style="color:${val_color};">${val}</div>
                    <div class="ma-kpi-lbl">${lbl}</div>
                </div>
            </div>`;

        $stats.html(
            kpi("fa-line-chart", "#EEF2FF", "#6366F1", avg, avg_color, __("Média da Turma")) +
            kpi("fa-check-circle", "#ECFDF5", "#10B981", approved, "#047857", __("Aprovados")) +
            kpi("fa-times-circle", "#FEF2F2", "#EF4444", failed, "#DC2626", __("Reprovados")) +
            kpi("fa-minus-circle", "#F3F4F6", "#9CA3AF", no_data, "#6B7280", __("S/Média")) +
            kpi("fa-users", "#F1F5F9", "#475569", total, "#111827", __("Total"))
        );
    }

    // -----------------------------------------------------------------------
    // Trimestral — save
    // -----------------------------------------------------------------------

    _collect_rows(idx) {
        const rows = [];
        this.$grid_area.find(".ma-grid tbody tr").each((i, tr) => {
            const $tr    = $(tr);
            const student = $tr.data("student");
            if (!student) return;
            const _iv  = (f) => { const n = parseInt($tr.find(`[data-field="${f}"]`).val()); return isNaN(n) ? null : n; };
            rows.push({
                student,
                acsp_1: _iv("acsp_1"),
                acsp_2: _iv("acsp_2"),
                acse_1: _iv("acse_1"),
                acse_2: _iv("acse_2"),
                acp:    _iv("acp"),
            });
        });
        return rows;
    }

    _save(idx) {
        const d    = this.data;
        const subj = d.subjects[idx];
        const rows = this._collect_rows(idx);

        frappe.call({
            method: "escola.escola.page.mapa_aproveitamento.mapa_aproveitamento.save_subject_grades",
            args: {
                class_group:   d.class_group,
                academic_term: d.academic_term,
                subject:       subj.subject,
                rows_json:     JSON.stringify(rows),
            },
            freeze: true,
            freeze_message: __("A guardar notas…"),
            callback: (r) => {
                if (!r.message) return;
                const resp = r.message;
                if (!resp.saved) {
                    frappe.show_alert({ message: __("Nenhuma nota para guardar."), indicator: "orange" });
                    return;
                }

                subj.grade_entry  = resp.grade_entry;
                subj.ge_docstatus = resp.ge_docstatus ?? 0;
                subj.status       = resp.status;
                // Enable Finalizar now that a grade_entry exists
                this.$grid_area.find(".ma-finalizar-btn").prop("disabled", false).removeAttr("title");

                const by_student = {};
                (resp.rows || []).forEach(sr => { by_student[sr.student] = sr; });
                const _ri = (v) => { const n = parseFloat(v); return (!isNaN(n) && v !== null && v !== undefined) ? String(Math.round(n)) : ""; };
                this.$grid_area.find(".ma-grid tbody tr").each((i, tr) => {
                    const sid = $(tr).data("student");
                    if (!sid || !by_student[sid]) return;
                    const sr  = by_student[sid];
                    const $tr = $(tr);
                    $tr.find("[data-field='macsp']").text(_ri(sr.macsp));
                    $tr.find("[data-field='macs']").text(_ri(sr.macs));
                    $tr.find("[data-field='mt']").text(_ri(sr.mt));
                });
                this._update_footer(idx);   // refresh KPIs + MT colours from saved values

                if (resp.grade_entry && !this.$grid_area.find(".ma-toolbar a").length) {
                    this.$grid_area.find(".ma-toolbar > div:first-child").append(
                        `<a href="/app/grade-entry/${encodeURIComponent(resp.grade_entry)}" target="_blank"
                            style="font-size:11px;color:#6366F1;margin-left:10px;">
                             <i class="fa fa-external-link"></i> ${resp.grade_entry}
                         </a>`
                    );
                }

                this._dirty.delete(idx);
                this.$tabs.find(`.ma-tab-btn[data-idx="${idx}"]`).removeClass("dirty");
                this._update_tab_status(idx, resp.status);
                this._update_footer(idx);
                frappe.show_alert({ message: __("Notas guardadas com sucesso."), indicator: "green" });
            },
        });
    }

    async _finalizar(idx) {
        const d    = this.data;
        const subj = d.subjects[idx];

        if (!subj.grade_entry) {
            frappe.show_alert({ message: __("Guarde as notas antes de finalizar."), indicator: "orange" });
            return;
        }

        // Fetch students with missing grades
        const wr = await frappe.call({
            method: "escola.escola.page.mapa_aproveitamento.mapa_aproveitamento.get_finalizar_warnings",
            args: { grade_entry: subj.grade_entry },
        });
        const missing = wr.message || [];

        let msg = __("Confirma a finalização da pauta de <b>{0}</b> para <b>{1}</b>?<br>"
            + "Após finalizar, as notas não poderão ser alteradas sem intervenção do Director Escolar.",
            [frappe.utils.escape_html(subj.subject_name), frappe.utils.escape_html(d.term_name)]);

        if (missing.length) {
            const names = missing.map(n => `<li>${frappe.utils.escape_html(n)}</li>`).join("");
            msg += `<br><br><span style="color:#b45309;font-weight:600;">
                        <i class="fa fa-warning"></i>&nbsp;
                        ${__("{0} aluno(s) sem notas completas (ACSP1, ACSP2, ACSE1, ACSE2, AT):", [missing.length])}
                    </span>
                    <ul style="margin:6px 0 0 16px;color:#92400e;">${names}</ul>`;
        }

        frappe.confirm(msg, () => {
            frappe.call({
                method: "escola.escola.page.mapa_aproveitamento.mapa_aproveitamento.submit_grade_entry",
                args: { grade_entry: subj.grade_entry },
                freeze: true,
                freeze_message: __("A finalizar pauta…"),
                callback: (r) => {
                    if (r.exc) return;
                    subj.ge_docstatus = 1;
                    this._show_subject(idx);
                    this._update_tab_status(idx, subj.status);
                    frappe.show_alert({ message: __("Pauta finalizada."), indicator: "green" });
                },
            });
        });
    }

    _update_tab_status(idx, status) {
        const color = this._dot_color(status);
        this.$tabs.find(`.ma-tab-btn[data-idx="${idx}"] .ma-dot`).css("background", color);
    }

    // -----------------------------------------------------------------------
    // Faltas & Comportamento — class-level, per term (Term Attendance)
    // -----------------------------------------------------------------------

    _show_attendance() {
        const d           = this.data;
        const prev_locked = !!d.attendance_prev_locked;
        const can_edit    = !!d.can_edit_attendance && !prev_locked;

        let actions;
        if (prev_locked) {
            actions = `<span style="background:#FEF3C7;color:#92400E;border-radius:20px;
                            padding:4px 14px;font-size:12px;font-weight:600;">
                   <i class="fa fa-lock"></i>&nbsp;${__("Finalize as pautas do período anterior ({0}) primeiro",
                        [frappe.utils.escape_html(d.prev_term_name || "")])}
               </span>`;
        } else if (!d.can_edit_attendance) {
            actions = `<span style="background:#FEF3C7;color:#92400E;border-radius:20px;
                            padding:4px 14px;font-size:12px;font-weight:600;">
                   <i class="fa fa-lock"></i>&nbsp;${__("Só o Director de Turma pode editar")}
               </span>`;
        } else {
            actions = `<button class="btn btn-default btn-sm ma-att-save-btn">
                   <i class="fa fa-floppy-o"></i>&nbsp;${__("Guardar")}
               </button>`;
        }

        const toolbar = `
            <div class="ma-toolbar" style="display:flex;align-items:center;
                                           justify-content:space-between;margin-bottom:10px;
                                           flex-wrap:wrap;gap:8px;">
                <div>
                    <span style="font-size:16px;font-weight:700;color:#1E293B;">
                        ${__("Faltas & Comportamento")}
                    </span>
                    <span style="font-size:12px;color:#9CA3AF;margin-left:8px;">
                        ${frappe.utils.escape_html(d.term_name)} — ${frappe.utils.escape_html(d.class_group_name)}
                    </span>
                </div>
                ${actions}
            </div>`;

        this.$grid_area.html(toolbar + this._build_attendance_html(d, can_edit));

        if (can_edit) {
            this._setup_attendance_events();
            this.$grid_area.find(".ma-att-save-btn").on("click", () => this._save_attendance());
        }
        this._update_att_footer();
    }

    _build_attendance_html(d, can_edit) {
        const att  = d.attendance || {};
        const opts = d.behaviour_options || [];
        const dis  = can_edit ? "" : " disabled";
        const _v   = (v) => (v !== null && v !== undefined) ? v : "";

        const rows_html = d.students.map((s, i) => {
            const a       = att[s.student] || {};
            const total   = (parseInt(a.justified_absences) || 0) + (parseInt(a.unjustified_absences) || 0);
            const totalSt = total > 0 ? "color:#92400E;font-weight:700;" : "color:#6B7280;";
            const risk    = a.at_risk
                ? `<span class="ma-risk-badge" title="${__("Faltas acima do limite")}">⚠</span>` : "";

            const num = (f) =>
                `<input type="number" class="ma-score ma-att-inp" data-field="${f}"
                        min="0" step="1" value="${_v(a[f])}"${dis}>`;

            const cur = a.comportamento || "";
            const options_html = [`<option value="">—</option>`].concat(
                opts.map(o =>
                    `<option value="${frappe.utils.escape_html(o)}"${o === cur ? " selected" : ""}>${frappe.utils.escape_html(o)}</option>`)
            ).join("");

            return `
                <tr data-student="${frappe.utils.escape_html(s.student)}">
                    <td style="color:#9CA3AF;font-size:11px;width:26px;">${i + 1}</td>
                    <td class="left" title="${frappe.utils.escape_html(s.student_name)}">
                        ${frappe.utils.escape_html(s.student_name)}
                    </td>
                    <td>${num("justified_absences")}</td>
                    <td>${num("unjustified_absences")}</td>
                    <td class="computed" data-field="total_absences" style="${totalSt}">${total || ""}</td>
                    <td data-field="risk">${risk}</td>
                    <td><select class="ma-att-comp" data-field="comportamento"${dis}>${options_html}</select></td>
                </tr>`;
        }).join("");

        return `
            <div style="overflow-x:auto;-webkit-overflow-scrolling:touch;">
            <table class="ma-grid">
                <thead>
                    <tr>
                        <th>#</th>
                        <th class="left" style="min-width:150px;">Nome</th>
                        <th title="Faltas justificadas">F. Justif.</th>
                        <th title="Faltas injustificadas">F. Injust.</th>
                        <th title="Total de faltas">Total</th>
                        <th title="Em risco por excesso de faltas">Risco</th>
                        <th title="Comportamento no período" style="min-width:140px;">Comportamento</th>
                    </tr>
                </thead>
                <tbody>${rows_html}</tbody>
            </table>
            </div>
            <div class="ma-stats" style="display:flex;gap:20px;padding:10px 4px;
                                         flex-wrap:wrap;margin-top:6px;"></div>
        `;
    }

    _setup_attendance_events() {
        const $area = this.$grid_area;
        $area.find(".ma-att-inp").on("input", (e) => {
            const $tr   = $(e.target).closest("tr");
            const j     = parseInt($tr.find('[data-field="justified_absences"]').val()) || 0;
            const u     = parseInt($tr.find('[data-field="unjustified_absences"]').val()) || 0;
            const total = j + u;
            $tr.find('[data-field="total_absences"]')
               .text(total || "")
               .css({ color: total > 0 ? "#92400E" : "#6B7280", "font-weight": total > 0 ? 700 : 400 });
            this._mark_att_dirty();
        });
        $area.find(".ma-att-comp").on("change", () => this._mark_att_dirty());
    }

    _mark_att_dirty() {
        if (!this._att_dirty) {
            this._att_dirty = true;
            this.$tabs.find(".ma-att-tab").addClass("dirty");
        }
    }

    _collect_attendance() {
        const rows = [];
        this.$grid_area.find(".ma-grid tbody tr").each((i, tr) => {
            const $tr     = $(tr);
            const student = $tr.data("student");
            if (!student) return;
            const _iv = (f) => { const n = parseInt($tr.find(`[data-field="${f}"]`).val()); return isNaN(n) ? 0 : n; };
            rows.push({
                student,
                justified_absences:   _iv("justified_absences"),
                unjustified_absences: _iv("unjustified_absences"),
                comportamento:        $tr.find('[data-field="comportamento"]').val() || null,
            });
        });
        return rows;
    }

    _save_attendance() {
        const d    = this.data;
        const rows = this._collect_attendance();

        frappe.call({
            method: "escola.escola.page.mapa_aproveitamento.mapa_aproveitamento.save_attendance",
            args: {
                class_group:   d.class_group,
                academic_term: d.academic_term,
                rows_json:     JSON.stringify(rows),
            },
            freeze: true,
            freeze_message: __("A guardar faltas…"),
            callback: (r) => {
                if (r.exc || !r.message || !r.message.saved) return;
                d.attendance = r.message.attendance || {};
                this.$grid_area.find(".ma-grid tbody tr").each((i, tr) => {
                    const $tr = $(tr);
                    const a   = d.attendance[$tr.data("student")];
                    if (!a) return;
                    const total = a.total_absences || 0;
                    $tr.find('[data-field="total_absences"]')
                       .text(total || "")
                       .css({ color: total > 0 ? "#92400E" : "#6B7280", "font-weight": total > 0 ? 700 : 400 });
                    $tr.find('[data-field="risk"]').html(
                        a.at_risk ? `<span class="ma-risk-badge" title="${__("Faltas acima do limite")}">⚠</span>` : ""
                    );
                });
                this._att_dirty = false;
                this.$tabs.find(".ma-att-tab").removeClass("dirty");
                this._update_att_footer();
                frappe.show_alert({ message: __("Faltas e comportamento guardados."), indicator: "green" });
            },
        });
    }

    _update_att_footer() {
        const $stats = this.$grid_area.find(".ma-stats");
        if (!$stats.length) return;
        const d   = this.data;
        const att = d.attendance || {};
        let at_risk = 0, with_comp = 0;
        (d.students || []).forEach(s => {
            const a = att[s.student] || {};
            if (a.at_risk) at_risk++;
            if (a.comportamento) with_comp++;
        });
        const total = (d.students || []).length;
        $stats.html(`
            <span style="font-size:13px;color:#EF4444;font-weight:700;">
                <i class="fa fa-exclamation-triangle"></i>&nbsp;${__("Em risco")}: ${at_risk}
            </span>
            <span style="font-size:13px;color:#10B981;font-weight:700;">
                <i class="fa fa-check-circle"></i>&nbsp;${__("Com comportamento")}: ${with_comp}
            </span>
            <span style="font-size:13px;color:#6B7280;">${__("Total")}: ${total}</span>
        `);
    }

    // -----------------------------------------------------------------------
    // Annual — render
    // -----------------------------------------------------------------------

    _render_annual() {
        const d = this.annual_data;
        if (!d) return;

        if (!d.subjects || !d.subjects.length) {
            this.$tabs.empty();
            this.$grid_area.html(this._empty_state(
                "fa-book",
                "Sem currículo activo",
                `A Turma <b>${frappe.utils.escape_html(d.class_group_name)}</b> não tem currículo activo com disciplinas.`
            ));
            return;
        }
        if (!d.students || !d.students.length) {
            this.$tabs.empty();
            this.$grid_area.html(this._empty_state(
                "fa-users",
                "Sem alunos activos",
                `Não existem alunos activos na Turma <b>${frappe.utils.escape_html(d.class_group_name)}</b>.`
            ));
            return;
        }
        if (!d.terms || !d.terms.length) {
            this.$tabs.empty();
            this.$grid_area.html(this._empty_state(
                "fa-calendar",
                "Sem períodos activos",
                `Não foram encontrados períodos activos para o ano lectivo <b>${frappe.utils.escape_html(d.academic_year)}</b>.`
            ));
            return;
        }

        this._render_annual_tabs();
        this._show_subject_annual(this._idx);
    }

    _render_annual_tabs() {
        const d = this.annual_data;
        let html = `<div style="display:flex;flex-wrap:wrap;">`;
        d.subjects.forEach((s, i) => {
            const active = i === this._idx ? " active" : "";
            html += `
                <button class="ma-tab-btn${active}" data-idx="${i}">
                    ${frappe.utils.escape_html(s.subject_name)}
                </button>`;
        });
        html += `</div>`;
        this.$tabs.html(html);
        this.$tabs.find(".ma-tab-btn").on("click", (e) => {
            const idx = parseInt($(e.currentTarget).data("idx"));
            this._idx = idx;
            this._render_annual_tabs();
            this._show_subject_annual(idx);
        });
    }

    _show_subject_annual(idx) {
        const d    = this.annual_data;
        const subj = d.subjects[idx];
        if (!subj) return;

        const header = `
            <div class="ma-toolbar" style="display:flex;align-items:center;
                                           justify-content:space-between;margin-bottom:10px;">
                <div>
                    <span style="font-size:16px;font-weight:700;color:#1E293B;">
                        ${frappe.utils.escape_html(subj.subject_name)}
                    </span>
                    <span style="font-size:12px;color:#9CA3AF;margin-left:8px;">
                        ${frappe.utils.escape_html(d.academic_year)} — ${frappe.utils.escape_html(d.class_group_name)}
                    </span>
                    <span style="font-size:11px;background:#F0F4FF;color:#6366F1;
                                 padding:2px 8px;border-radius:10px;margin-left:8px;font-weight:600;">
                        Vista Anual
                    </span>
                </div>
            </div>
        `;

        this.$grid_area.html(header + this._build_annual_grid_html(subj, d.students, d.terms));
        this._update_annual_footer(idx);
    }

    _build_annual_grid_html(subj, students, terms) {
        const row_map = {};
        (subj.rows || []).forEach(r => { row_map[r.student] = r; });

        const _f2 = (v) => { const n = parseFloat(v); return (!isNaN(n) && v !== null && v !== undefined) ? String(Math.round(n)) : ""; };
        const _mt_style = (v) => {
            if (v === null || v === undefined || v === "") return "";
            return parseFloat(v) >= 10 ? "color:#065F46;font-weight:700" : "color:#991B1B;font-weight:700";
        };

        const TERM_COLORS  = ["#1D4ED8", "#7C3AED", "#047857"];
        const SUB_LABELS   = ["ACSP1","ACSP2","MACSP","ACSE1","ACSE2","MACS","AT","MT","Falt.","Comp."];
        const SUB_KEYS     = ["acsp_1","acsp_2","macsp","acse_1","acse_2","macs","acp","mt","total_absences","comportamento"];
        const CALC_KEYS    = new Set(["macsp","macs","mt"]);
        const _abbr_c = (v) => {
            if (!v) return "";
            const m = {"Muito Bom":"MB","Bom":"B","Satisfatório":"S","Suficiente":"SF","Insatisfatório":"I","Mau":"M","Muito Mau":"MM"};
            return m[v] || v.substring(0,2).toUpperCase();
        };
        const _comp_color = (v) => {
            if (!v) return "color:#9CA3AF;";
            if (v === "Muito Bom" || v === "Bom") return "color:#065F46;font-weight:700;";
            if (v === "Insatisfatório" || v === "Mau" || v === "Muito Mau") return "color:#991B1B;font-weight:700;";
            return "color:#374151;font-weight:600;";
        };

        // Header row 1: term group cells + summary
        let head1 = `<th rowspan="2">#</th>
                     <th class="left" rowspan="2" style="min-width:150px;">Nome</th>`;
        terms.forEach((t, i) => {
            const bg = TERM_COLORS[i] || "#334155";
            head1 += `<th colspan="10" class="ma-annual-term-sep"
                          style="background:${bg};text-align:center;white-space:nowrap;">
                          ${frappe.utils.escape_html(t.term_name)}
                      </th>`;
        });
        head1 += `<th colspan="4" class="ma-annual-term-sep"
                      style="background:#1E293B;text-align:center;">Resumo Anual</th>`;

        // Header row 2: sub-column labels per term + MT1/MT2/MT3/MF
        let head2 = "";
        terms.forEach(() => {
            head2 += SUB_LABELS.map((l, li) =>
                `<th${li === 0 ? ' class="ma-annual-term-sep"' : ''} style="font-size:10px;">${l}</th>`
            ).join("");
        });
        head2 += `<th class="ma-annual-term-sep" style="font-size:10px;">MT1</th>
                  <th style="font-size:10px;">MT2</th>
                  <th style="font-size:10px;">MT3</th>
                  <th style="font-size:10px;background:#78350F;color:white;">MF</th>`;

        // Body rows
        const rows_html = students.map((s, i) => {
            const r    = row_map[s.student] || {};
            const trms = r.terms || [];

            let cells = "";
            terms.forEach((t, ti) => {
                const td  = trms[ti] || {};
                const abs = td.is_absent;
                cells += SUB_KEYS.map((k, ki) => {
                    const isFirst = ki === 0;
                    const sepCls  = isFirst ? ' class="ma-annual-term-sep"' : '';
                    if (abs) {
                        return `<td${sepCls} style="color:#D1D5DB;text-align:center;">—</td>`;
                    }
                    if (k === "total_absences") {
                        const n  = td.total_absences;
                        const v  = n != null ? n : "";
                        const st = (v !== "" && v > 0) ? "color:#92400E;font-weight:700;" : "color:#6B7280;";
                        return `<td${sepCls} style="text-align:center;font-size:12px;${st}">${v}</td>`;
                    }
                    if (k === "comportamento") {
                        const v   = td.comportamento || "";
                        const sh  = _abbr_c(v);
                        const st  = _comp_color(v);
                        return `<td${sepCls} style="text-align:center;font-size:12px;${st}"
                                    title="${frappe.utils.escape_html(v)}">${sh}</td>`;
                    }
                    const val  = _f2(td[k]);
                    const calc = CALC_KEYS.has(k);
                    const isMt = k === "mt";
                    const st   = isMt && val ? _mt_style(td[k]) : "";
                    const bg   = calc ? "background:#F9FAFB;" : "";
                    const fw   = calc ? "font-weight:700;" : "";
                    return `<td${sepCls} style="${bg}${fw}text-align:center;font-size:12px;${st}">${val}</td>`;
                }).join("");
            });

            // MT1, MT2, MT3 (always 3 slots)
            const mt_vals = [0,1,2].map(ti => {
                const td = trms[ti] || {};
                return td.is_absent ? null : (td.mt !== undefined ? td.mt : null);
            });
            cells += mt_vals.map((mt, mi) => {
                const val = _f2(mt);
                const st  = val ? _mt_style(mt) : "";
                const sep = mi === 0 ? ' class="ma-annual-term-sep"' : '';
                return `<td${sep} style="text-align:center;font-size:12px;${st}">${val}</td>`;
            }).join("");

            // MF
            const mf    = (r.mf !== undefined && r.mf !== null) ? r.mf : null;
            const mf_v  = _f2(mf);
            const mf_st = mf_v ? _mt_style(mf) : "";
            cells += `<td style="text-align:center;font-size:12px;font-weight:700;
                                 ${mf_st}${mf_v ? ";background:#FEF9C3" : ""}">${mf_v}</td>`;

            return `
                <tr data-student="${frappe.utils.escape_html(s.student)}">
                    <td style="color:#9CA3AF;font-size:11px;width:26px;">${i + 1}</td>
                    <td class="left" title="${frappe.utils.escape_html(s.student_name)}">
                        ${frappe.utils.escape_html(s.student_name)}
                    </td>
                    ${cells}
                </tr>`;
        }).join("");

        return `
            <div style="overflow-x:auto;-webkit-overflow-scrolling:touch;">
            <table class="ma-grid">
                <thead>
                    <tr>${head1}</tr>
                    <tr>${head2}</tr>
                </thead>
                <tbody>${rows_html}</tbody>
            </table>
            </div>
            <div class="ma-stats" style="display:flex;gap:20px;padding:10px 4px;
                                         flex-wrap:wrap;margin-top:6px;"></div>
        `;
    }

    _update_annual_footer(idx) {
        const $stats = this.$grid_area.find(".ma-stats");
        if (!$stats.length) return;
        const d    = this.annual_data;
        const subj = d.subjects[idx];
        if (!subj) return;

        let approved = 0, failed = 0, no_data = 0;
        (subj.rows || []).forEach(r => {
            if (r.mf === null || r.mf === undefined) { no_data++; return; }
            r.mf >= 10 ? approved++ : failed++;
        });
        const total = d.students ? d.students.length : 0;
        $stats.html(`
            <span style="font-size:13px;color:#10B981;font-weight:700;">
                <i class="fa fa-check-circle"></i>&nbsp;Aprovados: ${approved}
            </span>
            <span style="font-size:13px;color:#EF4444;font-weight:700;">
                <i class="fa fa-times-circle"></i>&nbsp;Reprovados: ${failed}
            </span>
            <span style="font-size:13px;color:#9CA3AF;font-weight:700;">
                <i class="fa fa-minus-circle"></i>&nbsp;S/Média: ${no_data}
            </span>
            <span style="font-size:13px;color:#6B7280;">Total: ${total}</span>
        `);
    }
}
