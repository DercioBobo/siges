# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Escola** is a Frappe/ERPNext app (`app_name = "escola"`) for Mozambican school management, built by EntreTech. The UI and all user-facing strings are in **Portuguese (pt-MZ)**. The app runs on a Frappe bench; all commands below assume you are in the bench root (not inside this repo).

## Common Commands

```bash
# Start development server
bench start

# Apply DB schema changes after modifying DocType JSONs
bench migrate

# Rebuild JS/CSS assets after modifying .js files in public/ or page JS
bench build --app escola

# Clear cache (needed after hooks.py or workspace changes)
bench clear-cache

# Run after adding new fixtures or School Settings fields
bench --site <site> execute escola.escola.setup.after_migrate

# Run a specific Python function manually
bench --site <site> execute escola.escola.doctype.billing_cycle.penalty.update_all_student_financial_statuses
```

There are no unit tests in this codebase.

## Architecture

### App layout

```
escola/
├── hooks.py                  # Entry point: doc_events, scheduler, fixtures, JS includes
├── escola/
│   ├── setup.py              # after_install/after_migrate: creates custom fields on ERPNext doctypes
│   ├── doctype/              # All DocTypes
│   ├── page/                 # Custom Frappe Pages (rich JS UIs)
│   ├── report/               # Query Reports (Python + JS)
│   └── workspace/            # 4 workspaces: escola, secretaria, professores, tesouraria
└── public/js/escola_utils.js # Shared frontend: escola.utils.auto_fill_academic_year()
```

### ERPNext integration (critical)

This app extends two standard ERPNext DocTypes with custom fields created in `setup.py`:

| DocType | Custom Field | Purpose |
|---|---|---|
| Sales Invoice | `escola_billing_cycle` | Links invoice to a Billing Cycle |
| Sales Invoice | `escola_student` | Links invoice to a Student |
| Sales Invoice Item | `escola_is_penalty_line` | Marks a row as a late-fee line |
| Customer | `escola_student` | Back-link from Customer to Student |

Every Student gets an ERPNext Customer created automatically on `after_insert` (`student.py`). The Customer name matches the student's full name.

### Billing flow

```
School Settings (singleton)
    └── Billing Schedule (per class, billing_mode: Mensal/Trimestral/Anual)
            └── [daily cron: run_due_schedules]
                    └── Billing Cycle (log doc, one per run)
                            └── Sales Invoice × N (one per active student)
```

- `billing_cycle.py → generate_invoices()` is the core generation function. It uses a **two-phase approach**: pre-create all Customers first, then create invoices — this prevents partial state if a Customer creation fails.
- Duplicate prevention is cross-cycle: checks `escola_student + billing_mode + posting_date` via SQL JOIN across all cycles.

### Penalty engine (`billing_cycle/penalty.py`)

- `_compute_penalty(due_date, settings)` — pure calculation, no side effects.
- Two modes (set in School Settings):
  - **Dinâmico**: display-only, never writes to the invoice.
  - **Adicionar à Factura**: writes a penalty line (`escola_is_penalty_line = 1`) to draft invoices. Applied by `apply_penalty_to_invoice()` (idempotent — removes old line before adding new).
- `apply_all_pending_penalties()` runs daily (only in "Adicionar à Factura" mode).
- `update_all_student_financial_statuses()` runs daily — recalculates `Student.financial_status` for every student with a non-cancelled invoice.

### Timetable system

```
Time Slot (master: label, start/end time, slot_type, shift, sort_order)
    └── Timetable (header: class_group + academic_term + status)
            └── Timetable Entry (child: day_of_week, time_slot, subject, teacher, is_double)
```

- Only one `status = "Activo"` timetable per `class_group + academic_term`. Setting a new one to Activo auto-archives the previous.
- Teacher is auto-filled from `Class Curriculum Line` when subject is selected in the form JS.
- The `timetable-view` page renders a grid filtered by the turma's shift (Manhã/Tarde).

### Curriculum → Teacher resolution

`Class Curriculum` (one active per `Class Group`) holds `Class Curriculum Line` rows with `subject + teacher + weekly_hours`. For non-specialist subjects (`Subject.is_specialist = 0`), the teacher falls back to `Class Group.class_teacher`. This resolution is used by both the timetable form JS and `timetable.py → get_curriculum_teacher()`.

### School Settings singleton

The single most important configuration document. Used everywhere via `frappe.get_single("School Settings")` or `frappe.db.get_single_value(...)`. Key fields include:
- `current_academic_year`, `invoice_posting_day`, `invoice_due_days`
- `penalty_mode`, `penalty_grace_days`, `penalty_increment_percent`, `penalty_max_percent`, `penalty_frequency`
- `auto_suspend_on_non_payment`, `suspension_threshold_weeks`

### Naming conventions

- Turma (Class Group) names follow the pattern: `{class_name} {letter}-{YY}` e.g. `3ª Classe A-26`. The letter is derived from count of existing groups for the class. Logic lives in `student_promotion.py → _turma_name()`.
- Teacher codes: auto-generated as `PROF-00001`.
- DocType naming series: `TUR-.####` (turma), `CUR-.YYYY.-.####` (curriculum), `HORT-.YYYY.-.####` (timetable).

### Doc events

Registered in `hooks.py`:
- `Student.on_update` → `class_group.sync_student_in_rosters` — keeps student_name in sync across all Class Group Student rows.
- `Sales Invoice.on_update_after_submit` and `on_cancel` → `penalty.on_sales_invoice_update` — recalculates `Student.financial_status`.

### Pages (custom rich UIs)

Each page under `escola/page/<name>/` has three files: `.json` (metadata/roles), `.py` (whitelisted API functions), `.js` (full UI). Pages are used for monitor/dashboard views where the standard DocType list view is insufficient:
- `invoice-monitor` — filterable invoice dashboard
- `schedule-monitor` — billing schedule status + upcoming timeline
- `timetable-view` — timetable grid with colour-coded subject badges
