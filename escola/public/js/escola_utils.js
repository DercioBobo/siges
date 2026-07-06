window.escola = window.escola || {};
escola.utils = escola.utils || {};

// ---------------------------------------------------------------------------
// Portal-first teachers — bounce desk visits to /portal-professor.
// Frappe v15 overwrites any home_page set in on_session_creation for System
// Users (LoginManager.set_user_info runs after the hook fires), so the
// redirect has to happen desk-side. The portal's "Ir para o Sistema" link
// sets a session flag that allows the desk for that browser tab.
// ---------------------------------------------------------------------------
$(function () {
    try {
        if (!window.location.pathname.startsWith("/app")) return;
        if (sessionStorage.getItem("escola_desk_ok")) return;
        const roles = (frappe.boot && frappe.boot.user && frappe.boot.user.roles) || [];
        const desk_first = ["System Manager", "Diretor Escolar", "Secretaria Escolar"];
        if (roles.includes("Professor") && !desk_first.some((r) => roles.includes(r))) {
            window.location.replace("/portal-professor");
        }
    } catch (e) {
        // never block desk boot over this
    }
});

// ---------------------------------------------------------------------------
// Year-end rollover reminder — dismissible checklist card for management.
// Backed by escola.escola.year_rollover.get_rollover_status; the daily
// scheduler sends the matching bell notification.
// ---------------------------------------------------------------------------
$(function () {
    try {
        if (!window.location.pathname.startsWith("/app")) return;
        const roles = (frappe.boot && frappe.boot.user && frappe.boot.user.roles) || [];
        if (!["System Manager", "Diretor Escolar", "Secretaria Escolar"].some((r) => roles.includes(r))) return;

        const SNOOZE_KEY = "escola_rollover_snooze";
        const snoozed_until = localStorage.getItem(SNOOZE_KEY);
        if (snoozed_until && new Date(snoozed_until) > new Date()) return;

        frappe.call({
            method: "escola.escola.year_rollover.get_rollover_status",
            callback(r) {
                const s = r.message;
                if (!s || !s.needs_action) return;
                render_rollover_banner(s);
            },
        });
    } catch (e) {
        // never block desk boot over this
    }

    function render_rollover_banner(s) {
        const esc = frappe.utils.escape_html;
        const headline = s.days_left >= 0
            ? __("O ano lectivo {0} termina em {1} dia(s).", [esc(s.current_year), s.days_left])
            : __("O ano lectivo {0} já terminou há {1} dia(s).", [esc(s.current_year), -s.days_left]);

        const items = s.steps.map((st) => `
            <div style="display:flex;align-items:center;gap:8px;padding:3px 0;font-size:12.5px;
                        color:${st.done ? "var(--text-muted)" : "var(--text-color)"};">
                <span style="width:16px;text-align:center;color:${st.done ? "var(--green-500,#22c55e)" : "var(--orange-500,#f97316)"};">
                    ${st.done ? "✓" : "○"}
                </span>
                <span style="${st.done ? "text-decoration:line-through;" : ""}">${esc(st.label)}</span>
            </div>`).join("");

        const $card = $(`
            <div style="position:fixed;bottom:20px;right:20px;z-index:1030;width:320px;
                        background:var(--fg-color,#fff);border:1px solid var(--border-color,#e2e8f0);
                        border-radius:12px;box-shadow:0 10px 30px rgba(0,0,0,.15);padding:14px 16px;">
                <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:8px;">
                    <div style="font-weight:700;font-size:13px;">📅 ${__("Preparar o novo ano lectivo")}</div>
                    <span class="rollover-close" style="cursor:pointer;color:var(--text-muted);font-size:16px;line-height:1;">×</span>
                </div>
                <div style="font-size:12.5px;color:var(--text-muted);margin:4px 0 8px;">${headline}</div>
                ${items}
                <div style="display:flex;gap:8px;margin-top:10px;">
                    <button class="btn btn-primary btn-xs rollover-next" style="flex:1;">${__("Próximo passo")}</button>
                    <button class="btn btn-default btn-xs rollover-snooze">${__("Lembrar em 3 dias")}</button>
                </div>
            </div>`);

        $card.find(".rollover-close, .rollover-snooze").on("click", () => {
            const until = new Date();
            until.setDate(until.getDate() + 3);
            localStorage.setItem("escola_rollover_snooze", until.toISOString());
            $card.remove();
        });

        $card.find(".rollover-next").on("click", () => {
            const next = (s.steps || []).find((st) => !st.done);
            if (!next) return;
            if (next.key === "year") frappe.new_doc("Academic Year");
            else if (next.key === "terms") frappe.set_route("Form", "Academic Year", s.next_year);
            else if (next.key === "turmas") frappe.set_route("List", "Student Promotion");
            else if (next.key === "abertura") frappe.new_doc("Abertura de Ano Lectivo");
            $card.remove();
        });

        $("body").append($card);
    }
});

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

// ---------------------------------------------------------------------------
// Shared searchable filter control  (pre-loaded options, type-to-filter)
// ---------------------------------------------------------------------------

escola.utils._inject_filter_styles = function () {
    if (document.getElementById("escola-fs-styles")) return;
    const s = document.createElement("style");
    s.id = "escola-fs-styles";
    s.textContent = `
.fs-wrap { position:relative; }
.fs-lbl  { font-size:11px;font-weight:700;color:var(--text-muted);text-transform:uppercase;
           letter-spacing:.6px;margin-bottom:5px;display:block; }
.fs-field { position:relative; display:flex; align-items:center; }
.fs-input { width:100%;padding:7px 46px 7px 11px;border:1.5px solid var(--border-color);
            border-radius:7px;font-size:13px;background:var(--control-bg,white);
            color:var(--text-color);outline:none;
            transition:border-color .15s,box-shadow .15s,background .15s;
            box-sizing:border-box;font-family:var(--font-stack);text-overflow:ellipsis; }
.fs-input:hover { border-color:var(--gray-400,#9ca3af); }
.fs-input:focus { border-color:var(--primary);
                  box-shadow:0 0 0 3px color-mix(in srgb,var(--primary) 14%,transparent); }
.fs-input.fs-has-val { font-weight:600; }
.fs-input::placeholder { color:var(--text-light);font-weight:400; }
/* trailing controls */
.fs-caret { position:absolute;right:10px;color:var(--text-muted);font-size:9px;
            cursor:pointer;user-select:none;pointer-events:all;
            transition:transform .18s ease,color .15s; }
.fs-field:focus-within .fs-caret { color:var(--primary); }
.fs-caret.fs-open { transform:rotate(180deg); }
.fs-clear { position:absolute;right:28px;width:17px;height:17px;display:none;
            align-items:center;justify-content:center;border-radius:50%;
            color:var(--text-muted);font-size:13px;line-height:1;cursor:pointer;
            user-select:none;pointer-events:all;transition:background .12s,color .12s; }
.fs-clear:hover { background:var(--subtle-fg,#f1f3f5);color:var(--text-color); }
.fs-clear.fs-show { display:flex; }
.fs-drop  { position:absolute;top:calc(100% + 5px);left:0;right:0;
            background:var(--fg-color,white);border:1px solid var(--border-color);
            border-radius:8px;box-shadow:0 10px 28px rgba(0,0,0,.16),0 2px 6px rgba(0,0,0,.06);
            z-index:1050;max-height:248px;overflow-y:auto;padding:4px;
            animation:fs-pop .13s ease; }
@keyframes fs-pop { from { opacity:0;transform:translateY(-4px); } to { opacity:1;transform:none; } }
.fs-opt   { display:flex;align-items:center;justify-content:space-between;gap:8px;
            padding:8px 11px;font-size:13px;cursor:pointer;color:var(--text-color);
            border-radius:5px;transition:background .08s; }
.fs-opt.fs-active:not(.fs-none) { background:var(--subtle-fg,#f3f4f6); }
.fs-opt.fs-sel { color:var(--primary);font-weight:600; }
.fs-opt.fs-sel.fs-active { background:color-mix(in srgb,var(--primary) 11%,transparent); }
.fs-check { color:var(--primary);font-size:11px;flex-shrink:0; }
.fs-opt-lbl { overflow:hidden;text-overflow:ellipsis;white-space:nowrap; }
.fs-none  { color:var(--text-muted);cursor:default;font-size:12px;font-style:italic;
            justify-content:flex-start; }
    `;
    document.head.appendChild(s);
};

/**
 * Create a searchable, pre-loaded filter select inside `parent_el`.
 *
 * Selection is index-based (never reads option values out of the DOM) so numeric
 * values such as the Academic Year "2026" can't be coerced by jQuery and silently
 * dropped. Supports full keyboard navigation (↑/↓/Enter/Esc) and an inline clear.
 *
 * @param {HTMLElement} parent_el
 * @param {Object} cfg
 *   label       {string}  - small-caps label shown above
 *   placeholder {string}  - input placeholder
 *   options     {Array}   - [{value, label}, ...]
 * @returns {{ get_value, set_value, set_options, on_change, clear }}
 */
escola.utils.make_filter_select = function (parent_el, { label, placeholder, options }) {
    escola.utils._inject_filter_styles();

    const $w = $(parent_el);
    $w.html(`
        <div class="fs-wrap">
            ${label ? `<span class="fs-lbl">${label}</span>` : ""}
            <div class="fs-field">
                <input class="fs-input" type="text" autocomplete="off" role="combobox"
                       aria-expanded="false"
                       placeholder="${placeholder || __("Selecionar…")}">
                <span class="fs-clear" title="${__("Limpar")}">×</span>
                <span class="fs-caret">▾</span>
            </div>
            <div class="fs-drop" style="display:none;"></div>
        </div>`);

    const $input = $w.find(".fs-input");
    const $drop  = $w.find(".fs-drop");
    const $caret = $w.find(".fs-caret");
    const $clear = $w.find(".fs-clear");

    let _val     = "";
    let _opts    = options ? [...options] : [];
    let _cb      = null;
    let _visible = [];   // currently shown options (after filtering)
    let _active  = -1;   // highlighted index into _visible

    function _is_open() { return $drop.is(":visible"); }

    function _sync_input_state() {
        const has = !!_val;
        $input.toggleClass("fs-has-val", has);
        $clear.toggleClass("fs-show", has);
    }

    function _render_drop() {
        if (!_visible.length) {
            $drop.html(`<div class="fs-opt fs-none">${__("Sem resultados")}</div>`);
            return;
        }
        $drop.html(_visible.map((o, i) => `
            <div class="fs-opt${o.value === _val ? " fs-sel" : ""}${i === _active ? " fs-active" : ""}"
                 data-i="${i}">
                <span class="fs-opt-lbl">${frappe.utils.escape_html(o.label)}</span>
                ${o.value === _val ? `<span class="fs-check">✓</span>` : ""}
            </div>`).join(""));
        _scroll_active();
    }

    function _scroll_active() {
        const el = $drop.find(".fs-opt.fs-active")[0];
        if (el) el.scrollIntoView({ block: "nearest" });
    }

    function _open(filter) {
        const q = (filter || "").toLowerCase();
        _visible = q ? _opts.filter(o => o.label.toLowerCase().includes(q)) : _opts.slice();
        _active  = _visible.findIndex(o => o.value === _val);
        if (_active < 0 && _visible.length) _active = 0;
        _render_drop();
        $drop.show();
        $caret.addClass("fs-open");
        $input.attr("aria-expanded", "true");
    }

    function _close() {
        $drop.hide();
        $caret.removeClass("fs-open");
        $input.attr("aria-expanded", "false");
    }

    function _restore() {
        const o = _opts.find(x => x.value === _val);
        $input.val(o ? o.label : "");
    }

    function _select(o) {
        _val = o.value;
        $input.val(o.label);
        _sync_input_state();
        _close();
        if (_cb) _cb(o.value);
    }

    function _do_clear(fire) {
        _val = "";
        $input.val("");
        _sync_input_state();
        if (fire && _cb) _cb("");
    }

    function _move(delta) {
        if (!_is_open()) { _open(""); return; }
        if (!_visible.length) return;
        _active = Math.max(0, Math.min(_visible.length - 1, _active + delta));
        _render_drop();
    }

    $input.on("focus", function () {
        const o = _opts.find(x => x.value === _val);
        _open(o && this.value === o.label ? "" : this.value);
    });
    $input.on("input", function () {
        if (_val) {
            const o = _opts.find(x => x.value === _val);
            if (!o || this.value !== o.label) { _val = ""; _sync_input_state(); }
        }
        _open(this.value);
    });
    $input.on("keydown", function (e) {
        switch (e.key) {
            case "ArrowDown": e.preventDefault(); _move(1); break;
            case "ArrowUp":   e.preventDefault(); _move(-1); break;
            case "Enter":
                if (_is_open() && _active >= 0 && _visible[_active]) {
                    e.preventDefault();
                    _select(_visible[_active]);
                }
                break;
            case "Escape":
                if (_is_open()) { e.preventDefault(); _close(); _restore(); }
                break;
        }
    });
    $input.on("blur", function () { setTimeout(() => { _close(); _restore(); }, 90); });

    $caret.on("pointerdown", function (e) {
        e.preventDefault();  // fires before blur for mouse, touch and pen
        _is_open() ? _close() : ($input[0].focus(), _open(""));
    });
    $clear.on("pointerdown", function (e) {
        e.preventDefault();
        _do_clear(true);
        $input[0].focus();
        _open("");
    });

    // Hover keeps the keyboard highlight in sync with the pointer
    $drop.on("mouseenter", ".fs-opt:not(.fs-none)", function () {
        _active = parseInt($(this).attr("data-i"), 10);
        $drop.find(".fs-opt").removeClass("fs-active");
        $(this).addClass("fs-active");
    });
    // Index-based selection — no value coercion, so clicks never silently fail
    $drop.on("pointerdown", ".fs-opt:not(.fs-none)", function (e) {
        e.preventDefault();
        const o = _visible[parseInt($(this).attr("data-i"), 10)];
        if (o) _select(o);
    });

    return {
        get_value:   ()     => _val,
        set_value:   (v)    => { _val = v || ""; _restore(); _sync_input_state(); },
        set_options: (opts) => { _opts = opts ? [...opts] : []; _do_clear(false); },
        on_change:   (fn)   => { _cb = fn; },
        clear:       ()     => { _do_clear(false); },
    };
};

// ---------------------------------------------------------------------------
// Sales Invoice — quick link to Student
// ---------------------------------------------------------------------------

frappe.ui.form.on("Sales Invoice", {
    refresh(frm) {
        if (!frm.doc.escola_student) return;

        frm.add_custom_button(
            frm.doc.escola_student,
            () => frappe.set_route("Form", "Student", frm.doc.escola_student),
            __("Aluno")
        );
    },
});
