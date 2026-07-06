import frappe
from frappe import _
from frappe.model.document import Document


@frappe.whitelist()
def get_current_academic_year():
    today = frappe.utils.today()
    year = frappe.db.get_value("Academic Year", {"is_active": 1}, "name")
    if year:
        return year
    year = frappe.db.get_value(
        "Academic Year",
        {"start_date": ("<=", today), "end_date": (">=", today)},
        "name",
    )
    if year:
        return year
    return frappe.db.get_value(
        "Academic Year",
        {"start_date": ("<=", today)},
        "name",
        order_by="start_date desc",
    )


@frappe.whitelist()
def get_current_academic_term(academic_year):
    today = frappe.utils.today()
    term = frappe.db.get_value(
        "Academic Term",
        {"academic_year": academic_year, "start_date": ("<=", today), "end_date": (">=", today)},
        "name",
    )
    if term:
        return term
    return frappe.db.get_value(
        "Academic Term",
        {"academic_year": academic_year, "start_date": ("<=", today)},
        "name",
        order_by="start_date desc",
    )


@frappe.whitelist()
def get_grade_entry_students(class_group, academic_year):
    """Return active students for the class, ordered by name."""
    rows = frappe.db.sql(
        """
        SELECT sga.student, s.full_name AS student_name
        FROM `tabStudent Group Assignment` sga
        JOIN `tabStudent` s ON s.name = sga.student
        WHERE sga.class_group = %s
          AND sga.academic_year = %s
          AND sga.status = 'Activa'
        ORDER BY s.full_name
        """,
        (class_group, academic_year),
        as_dict=True,
    )
    if not rows:
        return {"error": "no_students"}
    return rows


SCORE_FIELDS = ["acsp_1", "acsp_2", "acse_1", "acse_2", "acp", "macsp", "macs", "mt"]


class GradeEntry(Document):
    def validate(self):
        self._validate_term_belongs_to_year()
        self._validate_class_group_compatibility()
        self._validate_unique_entry()
        self._validate_rows_not_empty()
        self._validate_no_duplicate_students()
        self._validate_score_ranges()
        self._compute_macs_mt()
        self._calculate_class_summary()

    def on_update(self):
        self._restore_null_scores()

    def _restore_null_scores(self):
        """Frappe coerces None numeric values to 0 on DB write (get_valid_dict
        runs cint/flt), so 'sem nota' would become a real grade of 0 — corrupting
        averages on the next recalculation and making every pauta look Completa.
        Rewrite the empty fields as NULL after each save."""
        for row in self.grade_rows:
            empty = {f: None for f in SCORE_FIELDS if row.get(f) is None}
            if empty and row.name:
                frappe.db.set_value("Grade Entry Row", row.name, empty, update_modified=False)

    # ------------------------------------------------------------------
    # Header validations
    # ------------------------------------------------------------------

    def _validate_term_belongs_to_year(self):
        if not (self.academic_term and self.academic_year):
            return
        year = frappe.db.get_value("Academic Term", self.academic_term, "academic_year")
        if year != self.academic_year:
            frappe.throw(
                _("O Período <b>{0}</b> pertence ao Ano Lectivo <b>{1}</b>, "
                  "não a <b>{2}</b>.").format(self.academic_term, year, self.academic_year),
                title=_("Período incompatível"),
            )

    def _validate_class_group_compatibility(self):
        if not self.class_group:
            return
        cg = frappe.db.get_value(
            "Class Group", self.class_group,
            ["academic_year", "school_class"], as_dict=True,
        )
        if not cg:
            return
        if cg.academic_year != self.academic_year:
            frappe.throw(
                _("A Turma <b>{0}</b> pertence ao Ano Lectivo <b>{1}</b>, "
                  "não a <b>{2}</b>.").format(self.class_group, cg.academic_year, self.academic_year),
                title=_("Turma incompatível"),
            )

    def _validate_unique_entry(self):
        if not (self.class_group and self.academic_term and self.subject):
            return
        existing = frappe.db.get_value(
            "Grade Entry",
            {
                "class_group": self.class_group,
                "academic_term": self.academic_term,
                "subject": self.subject,
                "name": ("!=", self.name),
            },
            "name",
        )
        if existing:
            frappe.throw(
                _("Já existe uma Pauta para a Turma <b>{0}</b>, Período <b>{1}</b> "
                  "e Disciplina <b>{2}</b>: "
                  "<a href='/app/grade-entry/{3}'>{3}</a>.").format(
                    self.class_group, self.academic_term, self.subject, existing
                ),
                title=_("Pauta duplicada"),
            )

    # ------------------------------------------------------------------
    # Row validations
    # ------------------------------------------------------------------

    def _validate_rows_not_empty(self):
        if not self.grade_rows:
            frappe.throw(
                _("A Pauta não pode estar vazia. "
                  "Use o botão <b>Carregar Alunos</b> para preencher a tabela."),
                title=_("Tabela vazia"),
            )

    def _validate_no_duplicate_students(self):
        seen = set()
        for row in self.grade_rows:
            if row.student in seen:
                frappe.throw(
                    _("O aluno <b>{0}</b> aparece mais de uma vez na tabela.").format(row.student),
                    title=_("Aluno duplicado"),
                )
            seen.add(row.student)

    def _validate_score_ranges(self):
        score_fields = [
            ("acsp_1", "ACSP 1"), ("acsp_2", "ACSP 2"),
            ("acse_1", "ACSE 1"), ("acse_2", "ACSE 2"),
            ("acp",    "AT"),
        ]
        for row in self.grade_rows:
            if row.is_absent:
                continue
            for fname, label in score_fields:
                val = row.get(fname)
                if val is None:
                    continue
                if not (0 <= val <= 20):
                    frappe.throw(
                        _("{0} do aluno <b>{1}</b> está fora do intervalo (0–20): <b>{2}</b>.").format(
                            label, row.student, val
                        ),
                        title=_("Nota fora do intervalo"),
                    )

    # ------------------------------------------------------------------
    # Calculations
    #
    # MACSP = mean(ACSP scores)
    # MACS  = mean([MACSP if present] + [each ACSE score])
    # MT    = round((2 × MACS + ACP) / 3, 2)
    # ------------------------------------------------------------------

    def _compute_macs_mt(self):
        absent_fields = ["acsp_1", "acsp_2", "acse_1", "acse_2", "acp", "macsp", "macs", "mt"]
        for row in self.grade_rows:
            if row.is_absent:
                for f in absent_fields:
                    row.set(f, None)
                continue

            # MACSP — practical average
            acsp_vals = [v for v in [row.acsp_1, row.acsp_2] if v is not None]
            macsp = round(sum(acsp_vals) / len(acsp_vals)) if acsp_vals else None
            row.macsp = macsp

            # MACS — MACSP counts as ONE element alongside each written score
            acse_vals = [v for v in [row.acse_1, row.acse_2] if v is not None]
            macs_inputs = ([macsp] if macsp is not None else []) + acse_vals
            macs = round(sum(macs_inputs) / len(macs_inputs)) if macs_inputs else None
            row.macs = macs

            # MT
            if macs is not None and row.acp is not None:
                row.mt = round((2 * macs + row.acp) / 3)
            else:
                row.mt = None

    def _calculate_class_summary(self):
        self.total_approved = sum(1 for r in self.grade_rows if r.mt is not None and r.mt >= 10)
        self.total_failed = sum(
            1 for r in self.grade_rows
            if r.mt is not None and r.mt < 10 and not r.is_absent
        )


def repair_coerced_zero_rows():
    """One-off repair for rows written before the NULL-restore fix: a row where
    every score field is 0 and the student isn't absent was almost certainly an
    untouched student coerced by Frappe's numeric handling (empty → 0), not a
    student who genuinely scored 0 on all five assessments. Reset those to NULL.

    Run with:
    bench --site <site> execute escola.escola.doctype.grade_entry.grade_entry.repair_coerced_zero_rows
    """
    zero_conditions = " AND ".join(f"COALESCE({f}, 0) = 0" for f in SCORE_FIELDS)
    rows = frappe.db.sql(
        f"""
        SELECT name FROM `tabGrade Entry Row`
        WHERE {zero_conditions} AND COALESCE(is_absent, 0) = 0
          AND ({" OR ".join(f"{f} IS NOT NULL" for f in SCORE_FIELDS)})
        """,
        pluck="name",
    )
    for name in rows:
        frappe.db.set_value(
            "Grade Entry Row", name, {f: None for f in SCORE_FIELDS}, update_modified=False
        )
    frappe.db.commit()
    return {"repaired": len(rows)}


@frappe.whitelist()
def sync_grade_entry_students(doc_name):
    """Remove rows for students who are no longer active in the class. Preserves scores."""
    doc = frappe.get_doc("Grade Entry", doc_name)
    if not doc.grade_rows:
        return {"removed": 0, "kept": 0}

    unique_students = list({row.student for row in doc.grade_rows})
    active = set(
        frappe.get_all(
            "Student",
            filters={"name": ("in", unique_students), "current_status": "Activo"},
            pluck="name",
        )
    )

    original = len(doc.grade_rows)
    kept = [r for r in doc.grade_rows if r.student in active]
    removed = original - len(kept)

    if removed:
        doc.set("grade_rows", kept)
        doc.save(ignore_permissions=True)

    return {"removed": removed, "kept": len(kept)}
