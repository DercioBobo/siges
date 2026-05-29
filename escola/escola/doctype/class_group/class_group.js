frappe.ui.form.on("Class Group", {
    onload(frm) {
        escola.utils.auto_fill_academic_year(frm);
    },

    school_class(frm) {
        if (frm.is_new()) {
            _suggest_group_name(frm);
            _prefill_subjects(frm);
        }
    },

    academic_year(frm) {
        if (frm.is_new()) _suggest_group_name(frm);
    },

    refresh(frm) {
        if (!frm.is_new() && frm.doc.student_count > 0) {
            frm.set_df_property("school_class", "read_only", 1);
            frm.set_df_property("academic_year", "read_only", 1);
        }

        frm.set_query("class_teacher", () => ({ filters: { is_active: 1 } }));
        frm.set_query("teacher", "subject_teachers", (doc, cdt, cdn) => {
            const row = frappe.get_doc(cdt, cdn);
            if (!row || !row.subject) return { filters: { is_active: 1 } };
            return {
                filters: [
                    ["Teacher Subject", "subject", "=", row.subject],
                    ["Teacher", "is_active", "=", 1],
                ],
            };
        });

        if (frm.doc.school_class) {
            frm.set_query("subject", "subject_teachers", () => ({
                filters: [["School Class Subject", "parent", "=", frm.doc.school_class]],
            }));
        }

        const grid = frm.fields_dict["students"] && frm.fields_dict["students"].grid;
        if (grid) {
            grid.cannot_add_rows = true;
            grid.cannot_delete_rows = true;
        }

        if (!frm.is_new()) {
            frm.add_custom_button(__("Preencher Disciplinas"), () => _fill_subjects(frm), __("Acções"));

            frm.add_custom_button(__("Gerir Alunos"), () => manage_students_dialog(frm));
            frm.add_custom_button(__("Sincronizar Alunos"), () => _sync_class_group_students(frm), __("Acções"));

            frm.add_custom_button(
                __("Pauta de Notas"),
                () => frappe.new_doc("Grade Entry", { class_group: frm.doc.name }),
                __("Criar")
            );
            frm.add_custom_button(
                __("Faltas por Período"),
                () => frappe.new_doc("Term Attendance", { class_group: frm.doc.name }),
                __("Criar")
            );
            frm.add_custom_button(
                __("Promoção de Alunos"),
                () => frappe.new_doc("Student Promotion", { class_group: frm.doc.name }),
                __("Criar")
            );
            frm.add_custom_button(
                __("Ver Alocações"),
                () => frappe.set_route("List", "Student Group Assignment", { class_group: frm.doc.name }),
                __("Ver")
            );
            frm.add_custom_button(
                __("Horário"),
                () => _show_timetable_modal(frm),
                __("Ver")
            );
            frm.add_custom_button(
                __("Mapa de Aproveitamento"),
                () => {
                    frappe.route_options = { class_group: frm.doc.name };
                    frappe.set_route("mapa-aproveitamento");
                },
                __("Ver")
            );
            frm.add_custom_button(
                __("Mapa de Frequência"),
                () => {
                    frappe.route_options = { class_group: frm.doc.name };
                    frappe.set_route("pauta-frequencia");
                },
                __("Ver")
            );
            frm.add_custom_button(
                __("Reconstruir Pauta"),
                () => rebuild_roster(frm),
                __("Acções")
            );
        }

        _render_capacity_badge(frm);
    },
});

frappe.ui.form.on("Class Group", {
    async class_teacher(frm) {
        if (!frm.doc.class_teacher || !frm.doc.academic_year) return;

        const others = await frappe.db.get_list("Class Group", {
            filters: [
                ["class_teacher", "=", frm.doc.class_teacher],
                ["academic_year", "=", frm.doc.academic_year],
                ["name",          "!=", frm.doc.name || ""],
            ],
            fields: ["name", "group_name"],
            limit: 1,
        });

        if (!others.length) return;

        const other = others[0];
        frappe.confirm(
            __("Este professor já é Director de Turma de <a href='/app/class-group/{0}' target='_blank'><b>{1}</b></a> no mesmo Ano Lectivo. Quer mesmo continuar?",
                [other.name, frappe.utils.escape_html(other.group_name)]),
            () => { /* confirmed — keep value */ },
            () => frm.set_value("class_teacher", null)
        );
    },
});

frappe.ui.form.on("Class Group Subject Line", {
    subject(frm, cdt, cdn) {
        frappe.model.set_value(cdt, cdn, "teacher", null);
    },
});

// ---------------------------------------------------------------------------
// Capacity badge
// ---------------------------------------------------------------------------

function _render_capacity_badge(frm) {
    const count = frm.doc.student_count || 0;
    const max = frm.doc.max_students || 0;
    if (max > 0 && count >= max) {
        frm.dashboard.set_headline_alert(
            __("Turma com capacidade esgotada ({0}/{1} alunos)", [count, max]), "red"
        );
    } else if (max > 0) {
        frm.dashboard.set_headline_alert(
            __("{0}/{1} alunos", [count, max]),
            count / max >= 0.9 ? "orange" : "green"
        );
    }
}

// ---------------------------------------------------------------------------
// Styles  (injected once)
// ---------------------------------------------------------------------------

function _inject_styles() {
    if (document.getElementById("escola-mgr-styles")) return;
    const s = document.createElement("style");
    s.id = "escola-mgr-styles";
    s.textContent = `
/* ── shared ─────────────────────────────────────── */
.escmgr { font-family: var(--font-stack); }

.escmgr .section-title {
    font-size: 10px; font-weight: 700; text-transform: uppercase;
    letter-spacing: .7px; color: var(--text-muted); margin-bottom: 8px;
}

/* ── search bar ─────────────────────────────────── */
.escmgr .search-wrap { position: relative; margin-bottom: 12px; }
.escmgr .search-wrap svg { position: absolute; left: 11px; top: 50%;
    transform: translateY(-50%); color: var(--text-muted); pointer-events: none; }
.escmgr .search-inp {
    width: 100%; padding: 9px 14px 9px 36px;
    border: 1.5px solid var(--border-color); border-radius: 8px;
    font-size: 13px; background: var(--fg-color); color: var(--text-color);
    outline: none; transition: border-color .18s;
    box-sizing: border-box;
}
.escmgr .search-inp:focus { border-color: var(--primary); }

/* ── scrollable list box ────────────────────────── */
.escmgr .list-box {
    border: 1px solid var(--border-color); border-radius: 8px;
    overflow-y: auto; background: var(--fg-color);
}
.escmgr .list-box.tall { max-height: 260px; min-height: 120px; }
.escmgr .list-box.short { max-height: 200px; min-height: 80px; }

/* ── student card ───────────────────────────────── */
.escmgr .scard {
    display: flex; align-items: center; gap: 11px;
    padding: 9px 13px; cursor: pointer;
    border-bottom: 1px solid var(--border-color);
    transition: background .14s;
}
.escmgr .scard:last-child { border-bottom: none; }
.escmgr .scard:hover:not(.disabled) { background: var(--subtle-fg); }
.escmgr .scard.disabled { opacity: .42; cursor: default; }
.escmgr .scard.picked { background: var(--green-highlight, #f0fdf4); }

.escmgr .ava {
    width: 34px; height: 34px; border-radius: 50%; flex-shrink: 0;
    display: flex; align-items: center; justify-content: center;
    font-size: 12px; font-weight: 700; color: #fff; letter-spacing: .4px;
    box-shadow: 0 1px 3px rgba(0,0,0,.18);
}
.escmgr .sinfo { flex: 1; min-width: 0; }
.escmgr .sname {
    font-size: 13px; font-weight: 500; color: var(--text-color);
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.escmgr .sid { font-size: 11px; color: var(--text-muted); margin-top: 1px; }

.escmgr .sbadge {
    font-size: 11px; font-weight: 600; padding: 2px 9px;
    border-radius: 20px; flex-shrink: 0; white-space: nowrap;
}
.escmgr .b-enrolled { background: #fef3c7; color: #92400e; }
.escmgr .b-add      { background: #ede9fe; color: #6d28d9; }
.escmgr .b-picked   { background: #dcfce7; color: #166534; }

/* ── chips ──────────────────────────────────────── */
.escmgr .chips { display: flex; flex-wrap: wrap; gap: 7px; min-height: 32px; }
.escmgr .chip {
    display: inline-flex; align-items: center; gap: 5px;
    padding: 3px 8px 3px 4px; border-radius: 20px;
    background: #ede9fe; color: #6d28d9;
    font-size: 12px; font-weight: 500;
    animation: chipIn .14s ease;
}
.escmgr .chip-ava {
    width: 20px; height: 20px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: 8px; font-weight: 800; color: #fff; flex-shrink: 0;
}
.escmgr .chip-x {
    width: 15px; height: 15px; border-radius: 50%; cursor: pointer;
    display: flex; align-items: center; justify-content: center;
    background: rgba(109,40,217,.2); font-size: 10px; font-weight: 700;
    line-height: 1; transition: background .14s;
}
.escmgr .chip-x:hover { background: rgba(109,40,217,.4); }

@keyframes chipIn {
    from { transform: scale(.8); opacity: 0; }
    to   { transform: scale(1); opacity: 1; }
}

/* ── remove mode cards ──────────────────────────── */
.escmgr .scard .rm-btn {
    font-size: 11px; font-weight: 600; padding: 3px 10px;
    border-radius: 6px; border: 1.5px solid var(--red-300, #fca5a5);
    background: transparent; color: var(--red-500, #ef4444);
    cursor: pointer; flex-shrink: 0; transition: background .14s, color .14s;
}
.escmgr .scard .rm-btn:hover { background: var(--red-500, #ef4444); color: #fff; }

/* ── empty state ────────────────────────────────── */
.escmgr .empty {
    text-align: center; padding: 32px 16px;
    color: var(--text-muted); font-size: 13px;
}
.escmgr .empty svg { margin-bottom: 8px; opacity: .4; }

/* ── divider ────────────────────────────────────── */
.escmgr hr { border: none; border-top: 1px solid var(--border-color); margin: 14px 0; }

/* ── tab bar ────────────────────────────────────── */
.escmgr .tab-bar {
    display: flex; gap: 4px; margin-bottom: 16px;
    border-bottom: 2px solid var(--border-color); padding-bottom: 0;
}
.escmgr .tab-btn {
    padding: 7px 16px; font-size: 13px; font-weight: 600;
    color: var(--text-muted); background: none; border: none;
    cursor: pointer; border-bottom: 2px solid transparent;
    margin-bottom: -2px; transition: color .15s, border-color .15s;
}
.escmgr .tab-btn.active { color: var(--primary); border-bottom-color: var(--primary); }
.escmgr .tab-pane { display: none; }
.escmgr .tab-pane.active { display: block; }
    `;
    document.head.appendChild(s);
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const _COLORS = ["#7C3AED","#2563EB","#059669","#DC2626","#D97706","#0891B2","#DB2777","#0D9488","#9333EA","#EA580C"];

function _color(str) {
    let h = 0;
    for (let i = 0; i < str.length; i++) h = (h * 31 + str.charCodeAt(i)) & 0xffff;
    return _COLORS[h % _COLORS.length];
}

function _initials(name) {
    return (name || "?").split(" ").filter(Boolean).slice(0, 2).map(w => w[0]).join("").toUpperCase();
}

function _ava(name, size = 34) {
    const c = _color(name), ini = _initials(name);
    return `<div class="ava" style="width:${size}px;height:${size}px;background:${c}">${ini}</div>`;
}

function _scard_html(s, badge_html, extra = "") {
    return `
        <div class="scard ${extra}" data-id="${frappe.utils.escape_html(s.name)}"
             data-name="${frappe.utils.escape_html(s.full_name || s.name)}">
            ${_ava(s.full_name || s.name)}
            <div class="sinfo">
                <div class="sname">${frappe.utils.escape_html(s.full_name || s.name)}</div>
                <div class="sid">${frappe.utils.escape_html(s.name)}</div>
            </div>
            ${badge_html}
        </div>`;
}

// ---------------------------------------------------------------------------
// Combined Add + Remove dialog (tabbed)
// ---------------------------------------------------------------------------

function manage_students_dialog(frm) {
    _inject_styles();

    const enrolled = new Set((frm.doc.students || []).map(s => s.student));
    const selected = new Map(); // id → full_name

    const d = new frappe.ui.Dialog({
        title: `<span style="font-weight:700">${frm.doc.group_name}</span> · ${__("Gerir Alunos")}`,
        size: "large",
    });

    // Remove default footer padding mess
    d.$wrapper.find(".modal-footer").addClass("d-flex justify-content-between align-items-center");

    d.$body.html(`
        <div class="escmgr">
            <div class="tab-bar">
                <button class="tab-btn active" data-tab="add">➕ ${__("Adicionar")}</button>
                <button class="tab-btn" data-tab="remove">➖ ${__("Remover")}</button>
            </div>

            <!-- ADD TAB -->
            <div class="tab-pane active" id="tab-add">
                <div class="search-wrap">
                    <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
                        <path d="M11.742 10.344a6.5 6.5 0 1 0-1.397 1.398l3.85 3.85a1 1 0 0 0 1.415-1.415l-3.868-3.833zm-5.242 1.156a5 5 0 1 1 0-10 5 5 0 0 1 0 10z"/>
                    </svg>
                    <input class="search-inp" id="add-search"
                        type="text" placeholder="${__("Pesquisar aluno por nome…")}">
                </div>
                <div class="section-title">${__("Resultados")}</div>
                <div class="list-box tall" id="add-results">
                    <div class="empty">${__("A carregar…")}</div>
                </div>
                <hr>
                <div class="section-title">
                    ${__("Seleccionados")} (<span id="sel-count">0</span>)
                </div>
                <div class="chips" id="chips-wrap"></div>
            </div>

            <!-- REMOVE TAB -->
            <div class="tab-pane" id="tab-remove">
                <div class="search-wrap">
                    <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
                        <path d="M11.742 10.344a6.5 6.5 0 1 0-1.397 1.398l3.85 3.85a1 1 0 0 0 1.415-1.415l-3.868-3.833zm-5.242 1.156a5 5 0 1 1 0-10 5 5 0 0 1 0 10z"/>
                    </svg>
                    <input class="search-inp" id="rm-search"
                        type="text" placeholder="${__("Filtrar alunos da turma…")}">
                </div>
                <div class="section-title">${__("Alunos na Turma")} (${enrolled.size})</div>
                <div class="list-box tall" id="rm-list"></div>
            </div>
        </div>
    `);

    // ── Tab switching ────────────────────────────────────────────────
    d.$body.on("click", ".tab-btn", function () {
        const tab = $(this).data("tab");
        d.$body.find(".tab-btn").removeClass("active");
        d.$body.find(".tab-pane").removeClass("active");
        $(this).addClass("active");
        d.$body.find(`#tab-${tab}`).addClass("active");

        if (tab === "add") {
            d.set_primary_action(__("Atribuir"), () => submit_add());
            _update_add_btn();
            _do_search(d.$body.find("#add-search").val().trim());
        } else {
            d.set_primary_action(__("Fechar"), () => d.hide());
            _render_remove_list("");
        }
    });

    // ── ADD tab ──────────────────────────────────────────────────────
    let _search_timer;

    d.$body.find("#add-search").on("input", function () {
        clearTimeout(_search_timer);
        const q = this.value.trim();
        _search_timer = setTimeout(() => _do_search(q), q ? 300 : 0);
    });

    async function _do_search(q) {
        d.$body.find("#add-results").html(`<div class="empty">${__("A carregar…")}</div>`);
        const filters = [["current_status", "in", ["Activo", "Pendente de Turma"]]];
        if (q) filters.push(["full_name", "like", `%${q}%`]);
        const r = await frappe.call({
            method: "frappe.client.get_list",
            args: {
                doctype: "Student",
                filters,
                fields: ["name", "full_name"],
                limit_page_length: 50,
            },
        });
        _render_add_results(r.message || []);
    }

    function _render_add_results(students) {
        const $box = d.$body.find("#add-results").empty();
        if (!students.length) {
            $box.html(`<div class="empty"><div>${__("Nenhum aluno encontrado")}</div></div>`);
            return;
        }
        students.forEach(s => {
            const isEnrolled = enrolled.has(s.name);
            const isPicked = selected.has(s.name);
            const badge = isEnrolled
                ? `<span class="sbadge b-enrolled">${__("Já na turma")}</span>`
                : isPicked
                    ? `<span class="sbadge b-picked">✓ ${__("Seleccionado")}</span>`
                    : `<span class="sbadge b-add">+ ${__("Adicionar")}</span>`;
            const extra = isEnrolled ? "disabled" : isPicked ? "picked" : "";
            const $card = $(_scard_html(s, badge, extra));
            if (!isEnrolled) $card.on("click", () => _toggle(s.name, s.full_name || s.name));
            $box.append($card);
        });
    }

    function _toggle(id, name) {
        if (selected.has(id)) {
            selected.delete(id);
            d.$body.find(`#chips-wrap [data-id="${id}"]`).remove();
        } else {
            selected.set(id, name);
            const color = _color(name), ini = _initials(name);
            const $chip = $(`
                <div class="chip" data-id="${frappe.utils.escape_html(id)}">
                    <div class="chip-ava" style="background:${color}">${ini}</div>
                    <span>${frappe.utils.escape_html(name)}</span>
                    <div class="chip-x" title="${__("Remover")}">✕</div>
                </div>
            `);
            $chip.find(".chip-x").on("click", () => _toggle(id, name));
            d.$body.find("#chips-wrap").append($chip);
        }
        // Refresh card badge in results
        const $card = d.$body.find(`#add-results [data-id="${CSS.escape(id)}"]`);
        if (selected.has(id)) {
            $card.addClass("picked");
            $card.find(".sbadge").attr("class", "sbadge b-picked").text(`✓ ${__("Seleccionado")}`);
        } else {
            $card.removeClass("picked");
            $card.find(".sbadge").attr("class", "sbadge b-add").text(`+ ${__("Adicionar")}`);
        }
        _update_add_btn();
    }

    function _update_add_btn() {
        const n = selected.size;
        d.$body.find("#sel-count").text(n);
        d.get_primary_btn()
            .prop("disabled", n === 0)
            .text(n > 0 ? __("Atribuir {0} aluno(s)", [n]) : __("Atribuir"));
    }

    function submit_add() {
        const students = [...selected.keys()];
        if (!students.length) return;
        frappe.call({
            method: "escola.escola.doctype.class_group.class_group.add_students_to_group",
            args: { class_group_name: frm.doc.name, students: JSON.stringify(students) },
            freeze: true, freeze_message: __("A atribuir alunos…"),
            callback(r) {
                if (r.exc) return;
                d.hide();
                const { created, skipped, errors } = r.message;
                if (errors && errors.length) {
                    frappe.msgprint({
                        title: __("Alguns alunos não foram atribuídos"),
                        message: `<ul>${errors.map(e => `<li><b>${e.student}</b>: ${e.error}</li>`).join("")}</ul>`,
                        indicator: "orange",
                    });
                }
                const parts = [];
                if (created > 0) parts.push(__("{0} atribuído(s)", [created]));
                if (skipped > 0) parts.push(__("{0} já estava(m)", [skipped]));
                if (parts.length) frappe.show_alert({ message: parts.join(" · "), indicator: created > 0 ? "green" : "blue" });
                frm.reload_doc();
            },
        });
    }

    // ── REMOVE tab ───────────────────────────────────────────────────
    const _roster = (frm.doc.students || []).map(s => ({
        name: s.student,
        full_name: s.student_name || s.student,
    }));

    function _render_remove_list(filter) {
        const $box = d.$body.find("#rm-list").empty();
        const q = filter.toLowerCase();
        const list = q ? _roster.filter(s => (s.full_name || s.name).toLowerCase().includes(q)) : _roster;
        if (!list.length) {
            $box.html(`<div class="empty"><div>${q ? __("Nenhum resultado") : __("Turma sem alunos")}</div></div>`);
            return;
        }
        list.forEach(s => {
            const $card = $(_scard_html(s, `<button class="rm-btn">${__("Remover")}</button>`));
            $card.find(".rm-btn").on("click", (e) => {
                e.stopPropagation();
                _confirm_remove(s.name, s.full_name || s.name);
            });
            $box.append($card);
        });
    }

    function _confirm_remove(id, name) {
        frappe.confirm(
            __("Remover <b>{0}</b> desta turma?", [name]),
            () => {
                frappe.call({
                    method: "escola.escola.doctype.class_group.class_group.remove_student_from_group",
                    args: { class_group_name: frm.doc.name, student: id },
                    callback(r) {
                        if (r.exc) return;
                        frappe.show_alert({ message: __("Aluno removido da turma."), indicator: "green" });
                        // Remove from local roster and re-render
                        const idx = _roster.findIndex(s => s.name === id);
                        if (idx !== -1) _roster.splice(idx, 1);
                        enrolled.delete(id);
                        _render_remove_list(d.$body.find("#rm-search").val() || "");
                        frm.reload_doc();
                    },
                });
            }
        );
    }

    d.$body.on("input", "#rm-search", function () {
        _render_remove_list(this.value.trim());
    });

    // ── Init ─────────────────────────────────────────────────────────
    d.set_primary_action(__("Atribuir"), () => submit_add());
    _update_add_btn();

    d.show();
    setTimeout(() => {
        d.$body.find("#add-search").focus();
        _do_search("");
    }, 120);
}

// ---------------------------------------------------------------------------
// Auto-prefill subjects on new doc (school_class selected)
// ---------------------------------------------------------------------------

async function _prefill_subjects(frm) {
    if (!frm.doc.school_class) return;
    const r = await frappe.call({
        method: "escola.escola.doctype.class_group.class_group.get_subjects_for_school_class",
        args: { school_class: frm.doc.school_class },
    });
    if (!r.message || !r.message.length) return;
    frm.doc.subject_teachers = [];
    for (const s of r.message) {
        const row = frm.add_child("subject_teachers");
        row.subject = s.subject;
        row.is_specialist = s.is_specialist;
        if (s.teacher) row.teacher = s.teacher;
    }
    frm.refresh_field("subject_teachers");
}

// ---------------------------------------------------------------------------
// Fill subjects from School Class (manual button, saved docs)
// ---------------------------------------------------------------------------

async function _fill_subjects(frm) {
    const r = await frappe.call({
        method: "escola.escola.doctype.class_group.class_group.get_subjects_for_class_group",
        args: { class_group: frm.doc.name },
    });

    if (r.exc || !r.message || !r.message.length) {
        frappe.msgprint({
            message: __("Não foram encontradas disciplinas na ficha da Classe. "
                       + "Adicione as disciplinas na Classe antes de preencher."),
            title: __("Disciplinas em falta"),
            indicator: "orange",
        });
        return;
    }

    const existing = new Set((frm.doc.subject_teachers || []).map(r => r.subject));
    let added = 0;

    for (const s of r.message) {
        if (existing.has(s.subject)) continue;
        const row = frm.add_child("subject_teachers");
        row.subject       = s.subject;
        row.is_specialist = s.is_specialist;
        if (s.teacher)  row.teacher = s.teacher;
        added++;
    }

    frm.refresh_field("subject_teachers");

    if (added > 0) {
        frappe.show_alert({ message: __("{0} disciplina(s) adicionada(s).", [added]), indicator: "green" });
    } else {
        frappe.show_alert({ message: __("Todas as disciplinas já estão na lista."), indicator: "blue" });
    }
}

// ---------------------------------------------------------------------------
// Auto-suggest group_name on new docs
// ---------------------------------------------------------------------------

async function _suggest_group_name(frm) {
    if (!frm.doc.school_class || !frm.doc.academic_year) return;

    const [sc_val, count_r] = await Promise.all([
        frappe.db.get_value("School Class", frm.doc.school_class, "class_name"),
        frappe.call({
            method: "frappe.client.get_count",
            args: {
                doctype: "Class Group",
                filters: {
                    school_class:  frm.doc.school_class,
                    academic_year: frm.doc.academic_year,
                },
            },
        }),
    ]);

    const class_name = sc_val?.class_name || frm.doc.school_class;
    const n          = count_r?.message || 0;
    const letter     = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"[Math.min(n, 25)];
    const years      = (frm.doc.academic_year || "").match(/\d{4}/g) || [];
    const yy         = years.length ? years[years.length - 1].slice(-2) : "??";

    frm.set_value("group_name", `${class_name} ${letter}-${yy}`);
}

// ---------------------------------------------------------------------------
// Sync students (name + remove inactive)
// ---------------------------------------------------------------------------

function _sync_class_group_students(frm) {
    frappe.confirm(
        __("Alunos sem estado 'Activo' serão removidos e os nomes actualizados. Continuar?"),
        () => {
            frappe.call({
                method: "escola.escola.doctype.class_group.class_group.sync_class_group_students",
                args: { class_group_name: frm.doc.name },
                freeze: true,
                freeze_message: __("A sincronizar alunos…"),
                callback(r) {
                    if (!r.message) return;
                    const { removed, updated, kept } = r.message;
                    const parts = [];
                    if (removed > 0) parts.push(__("{0} removido(s)", [removed]));
                    if (updated > 0) parts.push(__("{0} nome(s) actualizado(s)", [updated]));
                    if (!parts.length) parts.push(__("Nenhuma alteração"));
                    frappe.show_alert({
                        message: parts.join(" · "),
                        indicator: removed > 0 ? "orange" : updated > 0 ? "blue" : "green",
                    });
                    if (removed > 0 || updated > 0) frm.reload_doc();
                },
            });
        }
    );
}

// ---------------------------------------------------------------------------
// Embedded timetable view
// ---------------------------------------------------------------------------

const _TT_PALETTE = [
    "#6366F1","#10B981","#F59E0B","#EF4444","#8B5CF6",
    "#EC4899","#14B8A6","#F97316","#0EA5E9","#84CC16",
    "#A855F7","#06B6D4","#D97706","#059669","#7C3AED",
];

const _TT_DAY = {
    "Segunda-Feira": "2ª Feira",
    "Terça-Feira":   "3ª Feira",
    "Quarta-Feira":  "4ª Feira",
    "Quinta-Feira":  "5ª Feira",
    "Sexta-Feira":   "6ª Feira",
};

function _show_timetable_modal(frm) {
    if (!frm.doc.academic_year) {
        frappe.msgprint({ message: __("Defina o Ano Lectivo para ver o horário."), indicator: "orange" });
        return;
    }

    const d = new frappe.ui.Dialog({
        title: `${frm.doc.group_name} · ${__("Horário")}`,
        size: "extra-large",
    });

    d.$body.html(`
        <div style="text-align:center;padding:50px;color:#9CA3AF;">
            <i class="fa fa-spinner fa-spin fa-2x"></i>
            <div style="margin-top:10px;font-size:13px;">${__("A carregar horário…")}</div>
        </div>`);

    d.show();

    frappe.call({
        method: "escola.escola.page.timetable_view.timetable_view.get_timetable_data",
        args: { class_group: frm.doc.name, academic_year: frm.doc.academic_year },
        callback(r) {
            if (r.exc) { d.$body.html(""); return; }
            _tt_render(d.$body, r.message, frm.doc.name, frm.doc.academic_year);
        },
    });
}

function _tt_render(wrapper, data, cg_name, academic_year) {
    if (!data) return;

    const color_cache = {};
    let palette_idx = 0;

    function subject_color(code, server_color) {
        if (color_cache[code]) return color_cache[code];
        const c = (server_color && server_color.trim())
            ? server_color.trim()
            : _TT_PALETTE[palette_idx++ % _TT_PALETTE.length];
        return (color_cache[code] = c);
    }

    (data.subjects_summary || []).forEach(s => subject_color(s.subject_code, s.color));

    if (!data.found) {
        const $empty = $(`
            <div style="text-align:center;padding:50px 20px;background:#F9FAFB;
                        border-radius:10px;border:1px dashed #E5E7EB;margin:8px 0;">
                <i class="fa fa-calendar-o fa-2x" style="color:#D1D5DB;"></i>
                <div style="color:#374151;font-weight:700;margin-top:12px;">
                    ${__("Sem horário activo")}
                </div>
                <p style="color:#6B7280;margin:6px 0 14px;font-size:13px;">
                    ${__("Não existe um horário activo para este período.")}
                </p>
                <button class="btn btn-primary btn-xs btn-create-tt">
                    <i class="fa fa-plus"></i>&nbsp;${__("Criar Horário")}
                </button>
            </div>`);
        $empty.find(".btn-create-tt").on("click", () => {
            frappe.new_doc("Timetable", { class_group: cg_name, academic_year });
        });
        wrapper.empty().append($empty);
        return;
    }

    const html = [
        _tt_html_grid(data, subject_color),
        _tt_html_legend(data.subjects_summary, subject_color),
    ].join("");

    wrapper.html(html);
}

function _tt_html_grid(data, subject_color) {
    const { time_slots, days, grid, timetable_name } = data;
    if (!time_slots || !time_slots.length) return "";

    const col_pct = Math.floor(82 / days.length);

    const header_cells = days.map(d =>
        `<th style="background:#1E293B;color:white;border-radius:6px;padding:10px 6px;
                    font-size:12px;font-weight:700;text-align:center;width:${col_pct}%;">
            ${_TT_DAY[d] || d}
        </th>`
    ).join("");

    const rows = time_slots.map(slot => {
        const is_break = slot.slot_type === "Intervalo" || slot.slot_type === "Borla";
        const time_cell = `
            <td style="background:#F3F4F6;border-radius:6px;padding:7px 5px;
                       text-align:center;vertical-align:middle;">
                <div style="font-size:11px;font-weight:700;color:#374151;">
                    ${frappe.utils.escape_html(slot.label)}
                </div>
            </td>`;

        if (is_break) {
            const label = slot.slot_type === "Intervalo" ? "— INTERVALO —" : "— BORLA —";
            return `<tr>
                ${time_cell}
                <td colspan="${days.length}"
                    style="background:#F1F5F9;border-radius:6px;padding:7px 12px;
                           font-size:11px;color:#94A3B8;font-weight:700;
                           text-align:center;letter-spacing:2px;">
                    ${label}
                </td>
            </tr>`;
        }

        const day_cells = days.map(day => {
            const cell = (grid[day] || {})[slot.name];
            if (!cell || !cell.subject_code) {
                return `<td style="background:#F9FAFB;border-radius:6px;min-height:56px;"></td>`;
            }
            const color = subject_color(cell.subject_code, cell.color);
            return `
                <td style="background:white;border-radius:6px;padding:5px 3px;vertical-align:middle;">
                    <div style="background:${color}1A;border-left:3px solid ${color};
                                border-radius:4px;padding:6px 8px;min-height:54px;">
                        <div style="font-size:13px;font-weight:800;color:${color};letter-spacing:.5px;">
                            ${frappe.utils.escape_html(cell.subject_code)}
                        </div>
                        <div style="font-size:10px;color:#6B7280;margin-top:2px;line-height:1.3;">
                            ${frappe.utils.escape_html(cell.teacher || "")}
                        </div>
                    </div>
                </td>`;
        }).join("");

        return `<tr>${time_cell}${day_cells}</tr>`;
    }).join("");

    return `
        <div style="text-align:right;margin-bottom:8px;">
            <a href="/app/timetable/${encodeURIComponent(timetable_name)}"
               class="btn btn-default btn-xs" target="_blank">
                <i class="fa fa-pencil"></i>&nbsp;${__("Editar Horário")}
            </a>
        </div>
        <div style="overflow-x:auto;-webkit-overflow-scrolling:touch;">
        <table style="width:100%;border-collapse:separate;border-spacing:3px;table-layout:fixed;">
            <thead>
                <tr>
                    <th style="width:10%;min-width:82px;background:#F3F4F6;border-radius:6px;
                               padding:10px 6px;font-size:11px;color:#6B7280;font-weight:700;
                               text-align:center;">HORÁRIO</th>
                    ${header_cells}
                </tr>
            </thead>
            <tbody>${rows}</tbody>
        </table>
        </div>`;
}

function _tt_html_legend(summary, subject_color) {
    if (!summary || !summary.length) return "";

    const badges = summary.map(s => {
        const color = subject_color(s.subject_code, s.color);
        return `
            <div style="display:flex;align-items:center;gap:6px;background:#F9FAFB;
                        border-radius:6px;padding:6px 10px;">
                <div style="width:12px;height:12px;background:${color};border-radius:3px;flex-shrink:0;"></div>
                <span style="font-size:12px;font-weight:800;color:${color};">
                    ${frappe.utils.escape_html(s.subject_code)}
                </span>
                <span style="font-size:12px;color:#374151;">
                    ${frappe.utils.escape_html(s.subject)}
                </span>
                <span style="font-size:11px;color:#9CA3AF;">
                    (${s.slots} aula${s.slots !== 1 ? "s" : ""}/sem.)
                </span>
            </div>`;
    }).join("");

    return `
        <div style="margin-top:16px;background:white;border:1px solid #E5E7EB;
                    border-radius:10px;padding:14px 18px;">
            <div style="font-size:11px;color:#9CA3AF;font-weight:700;
                        margin-bottom:10px;letter-spacing:1px;">LEGENDA</div>
            <div style="display:flex;flex-wrap:wrap;gap:8px;">${badges}</div>
        </div>`;
}

// ---------------------------------------------------------------------------
// Rebuild roster
// ---------------------------------------------------------------------------

function rebuild_roster(frm) {
    frappe.confirm(
        __("Isto irá reconstruir a lista de alunos a partir das Alocações de Turma activas. Continuar?"),
        () => {
            frappe.call({
                method: "escola.escola.doctype.class_group.class_group.rebuild_roster",
                args: { class_group_name: frm.doc.name },
                freeze: true, freeze_message: __("A reconstruir a pauta…"),
                callback(r) {
                    if (r.message !== undefined) {
                        frappe.show_alert({
                            message: __("Pauta reconstruída com {0} aluno(s).", [r.message]),
                            indicator: "green",
                        });
                        frm.reload_doc();
                    }
                },
            });
        }
    );
}
