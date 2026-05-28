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
.fs-input { width:100%;padding:7px 28px 7px 10px;border:1.5px solid var(--border-color);
            border-radius:6px;font-size:13px;background:var(--control-bg,white);
            color:var(--text-color);outline:none;transition:border-color .15s,box-shadow .15s;
            box-sizing:border-box;font-family:var(--font-stack); }
.fs-input:focus { border-color:var(--primary);
                  box-shadow:0 0 0 3px color-mix(in srgb,var(--primary) 12%,transparent); }
.fs-input::placeholder { color:var(--text-light); }
.fs-caret { position:absolute;right:9px;color:var(--text-muted);font-size:10px;
            cursor:pointer;user-select:none;pointer-events:all; }
.fs-drop  { position:absolute;top:calc(100% + 4px);left:0;right:0;
            background:var(--fg-color,white);border:1.5px solid var(--primary);
            border-radius:6px;box-shadow:0 6px 20px rgba(0,0,0,.13);
            z-index:1050;max-height:220px;overflow-y:auto; }
.fs-opt   { padding:8px 12px;font-size:13px;cursor:pointer;color:var(--text-color);
            transition:background .1s; }
.fs-opt:hover:not(.fs-none) { background:var(--subtle-fg,#f3f4f6); }
.fs-opt.fs-sel { background:color-mix(in srgb,var(--primary) 10%,transparent);
                 color:var(--primary);font-weight:600; }
.fs-none  { color:var(--text-muted);cursor:default;font-size:12px;font-style:italic; }
    `;
    document.head.appendChild(s);
};

/**
 * Create a searchable, pre-loaded filter select inside `parent_el`.
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
                <input class="fs-input" type="text" autocomplete="off"
                       placeholder="${placeholder || __("Selecionar…")}">
                <span class="fs-caret">▾</span>
            </div>
            <div class="fs-drop" style="display:none;"></div>
        </div>`);

    const $input = $w.find(".fs-input");
    const $drop  = $w.find(".fs-drop");
    const $caret = $w.find(".fs-caret");

    let _val  = "";
    let _opts = options ? [...options] : [];
    let _cb   = null;

    function _show(filter) {
        const q = (filter || "").toLowerCase();
        const visible = q ? _opts.filter(o => o.label.toLowerCase().includes(q)) : _opts;
        $drop.html(
            visible.length
                ? visible.map(o =>
                    `<div class="fs-opt${o.value === _val ? " fs-sel" : ""}"
                          data-v="${frappe.utils.escape_html(o.value)}">
                        ${frappe.utils.escape_html(o.label)}
                     </div>`).join("")
                : `<div class="fs-opt fs-none">${__("Sem resultados")}</div>`
        ).show();
    }

    function _close()  { $drop.hide(); }
    function _restore() {
        const o = _opts.find(x => x.value === _val);
        $input.val(o ? o.label : "");
    }

    $input.on("focus", function () {
        const o = _opts.find(x => x.value === _val);
        _show(o && this.value === o.label ? "" : this.value);
    });
    $input.on("input",  function () {
        if (_val) { const o = _opts.find(x => x.value === _val); if (!o || this.value !== o.label) _val = ""; }
        _show(this.value);
    });
    $input.on("blur", function () { setTimeout(() => { _close(); _restore(); }, 80); });
    $caret.on("pointerdown", function (e) {
        e.preventDefault();  // pointerdown fires before blur for all pointer types
        $drop.is(":visible") ? _close() : ($input[0].focus(), _show(""));
    });
    $drop.on("pointerdown", ".fs-opt:not(.fs-none)", function (e) {
        e.preventDefault();  // pointerdown fires before blur — no race for tap, click or touch
        const v = $(this).data("v");
        const o = _opts.find(x => x.value === v);
        if (!o) return;
        _val = v;
        $input.val(o.label);
        _close();
        if (_cb) _cb(v);
    });

    return {
        get_value:   ()     => _val,
        set_value:   (v)    => { _val = v || ""; _restore(); },
        set_options: (opts) => { _opts = opts ? [...opts] : []; _val = ""; $input.val(""); },
        on_change:   (fn)   => { _cb = fn; },
        clear:       ()     => { _val = ""; $input.val(""); },
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
