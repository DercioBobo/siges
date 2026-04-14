import frappe
from frappe import _
from frappe.model.document import Document


class AcademicClosure(Document):
    def validate(self):
        self._validate_uniqueness()
        self._validate_no_duplicate_students()
        self._validate_average_ranges()
        self._recalculate_summary()

    def _validate_uniqueness(self):
        existing = frappe.db.get_value(
            "Academic Closure",
            {
                "class_group": self.class_group,
                "academic_year": self.academic_year,
                "name": ("!=", self.name),
            },
            "name",
        )
        if existing:
            frappe.throw(
                _("Já existe um Fecho Académico ({0}) para a turma {1} no ano lectivo {2}.").format(
                    existing, self.class_group, self.academic_year
                )
            )

    def _validate_no_duplicate_students(self):
        seen = set()
        for row in self.closure_rows:
            if row.student in seen:
                frappe.throw(
                    _("O aluno {0} está duplicado no Fecho Académico.").format(row.student)
                )
            seen.add(row.student)

    def _validate_average_ranges(self):
        for row in self.closure_rows:
            if row.overall_average and (row.overall_average < 0 or row.overall_average > 20):
                frappe.throw(
                    _("A média do aluno {0} deve estar entre 0 e 20. Valor: {1}.").format(
                        row.student, row.overall_average
                    )
                )

    def _recalculate_summary(self):
        rows = self.closure_rows or []
        self.total_students = len(rows)
        self.promoted_students = sum(1 for r in rows if r.final_decision == "Promovido")
        self.retained_students = sum(1 for r in rows if r.final_decision == "Retido")
        self.concluded_students = sum(1 for r in rows if r.final_decision == "Concluído")


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_class_groups_with_promotions(doctype, txt, searchfield, start, page_len, filters):
    """Custom search: only Class Groups that have a Student Promotion (optionally filtered by academic_year)."""
    import json
    if isinstance(filters, str):
        filters = json.loads(filters)
    filters = filters or {}

    academic_year = filters.get("academic_year")
    values = {"txt": f"%{txt}%", "start": int(start), "page_len": int(page_len)}

    conds = ["cg.is_active = 1", f"cg.`{searchfield}` LIKE %(txt)s"]
    if academic_year:
        conds.append("sp.academic_year = %(academic_year)s")
        values["academic_year"] = academic_year

    sql = """
        SELECT DISTINCT cg.name
        FROM `tabClass Group` cg
        INNER JOIN `tabStudent Promotion` sp ON sp.class_group = cg.name
        WHERE {where}
        ORDER BY cg.name
        LIMIT %(start)s, %(page_len)s
    """.format(where=" AND ".join(conds))

    return frappe.db.sql(sql, values)


@frappe.whitelist()
def load_promotions(doc_name):
    """Thin wrapper — delegates to load_promotions_by_params using the saved doc."""
    doc = frappe.get_doc("Academic Closure", doc_name)
    if not doc.class_group or not doc.academic_year:
        frappe.throw(_("Preencha o Ano Lectivo e a Turma antes de carregar as promoções."))
    return load_promotions_by_params(doc.class_group, doc.academic_year)


@frappe.whitelist()
def load_promotions_by_params(class_group, academic_year):
    """
    Fetch Student Promotion rows for the given class_group + academic_year.
    Also pulls per-student averages from Annual Assessment when available.
    Can be called before the Academic Closure document is saved.
    """
    promotion = frappe.db.get_value(
        "Student Promotion",
        {"class_group": class_group, "academic_year": academic_year},
        "name",
    )
    if not promotion:
        return {"error": "no_promotion"}

    promo_rows = frappe.get_all(
        "Student Promotion Row",
        filters={"parent": promotion},
        fields=["student", "decision", "remarks"],
        order_by="student asc",
    )
    if not promo_rows:
        return {"error": "no_rows"}

    # Per-student averages from Annual Assessment
    avg_map = {}
    annual = frappe.db.get_value(
        "Annual Assessment",
        {"class_group": class_group, "academic_year": academic_year},
        "name",
    )
    if annual:
        ann_rows = frappe.get_all(
            "Annual Assessment Row",
            filters={"parent": annual},
            fields=["student", "final_grade"],
        )
        by_student = {}
        for r in ann_rows:
            by_student.setdefault(r.student, []).append(r.final_grade)
        for student, grades in by_student.items():
            avg_map[student] = round(sum(grades) / len(grades), 1) if grades else 0

    return {
        "rows": [
            {
                "student":        r.student,
                "final_decision": r.decision,
                "overall_average": avg_map.get(r.student, 0),
                "remarks":        r.remarks or "",
            }
            for r in promo_rows
        ]
    }


@frappe.whitelist()
def load_students_for_closure(class_group, academic_year):
    """
    Load active students for a closure from Student Group Assignment.
    Used for auto-fill when a turma is selected — does not require a Student Promotion.
    Also enriches with averages from Annual Assessment if one exists.
    """
    sgas = frappe.get_all(
        "Student Group Assignment",
        filters={"class_group": class_group, "academic_year": academic_year, "status": "Activa"},
        fields=["student"],
        order_by="student asc",
    )
    if not sgas:
        return {"error": "no_students"}

    # Optionally enrich with averages from Annual Assessment
    avg_map = {}
    annual = frappe.db.get_value(
        "Annual Assessment",
        {"class_group": class_group, "academic_year": academic_year},
        "name",
    )
    if annual:
        ann_rows = frappe.get_all(
            "Annual Assessment Row",
            filters={"parent": annual},
            fields=["student", "final_grade"],
        )
        by_student = {}
        for r in ann_rows:
            by_student.setdefault(r.student, []).append(r.final_grade)
        for student, grades in by_student.items():
            avg_map[student] = round(sum(grades) / len(grades), 1) if grades else 0

    return {
        "rows": [
            {
                "student":               s.student,
                "final_decision":        "",
                "total_failed_subjects": 0,
                "overall_average":       avg_map.get(s.student, 0),
                "remarks":               "",
            }
            for s in sgas
        ]
    }


@frappe.whitelist()
def create_report_cards(doc_name):
    """
    Create or update one Report Card per student in closure_rows.
    - New students: full Report Card is created with subject rows + final_decision.
    - Existing students: subject rows are refreshed and final_decision is updated.
    Per-subject data is re-calculated from Grade Entry via _build_report_card_data,
    since Annual Assessment Row only stores per-student aggregates, not per-subject rows.
    """
    from escola.escola.doctype.report_card.report_card import _build_report_card_data

    doc = frappe.get_doc("Academic Closure", doc_name)

    if not doc.closure_rows:
        return {"error": "no_closure_rows"}

    annual = frappe.db.get_value(
        "Annual Assessment",
        {"class_group": doc.class_group, "academic_year": doc.academic_year},
        "name",
    )
    if not annual:
        return {"error": "no_annual_assessment"}

    created, updated, errors = [], [], []

    for row in doc.closure_rows:
        try:
            data = _build_report_card_data(annual, row.student, doc.school_class)
            if not data or not data["rows"]:
                errors.append(row.student)
                continue

            # Closure row is authoritative for the final decision
            final_decision = row.final_decision or data.get("final_decision")

            existing = frappe.db.get_value(
                "Report Card",
                {"student": row.student, "academic_year": doc.academic_year},
                "name",
            )

            if existing:
                rc = frappe.get_doc("Report Card", existing)
                rc.set("report_card_rows", [])
                for r in data["rows"]:
                    rc.append("report_card_rows", r)
                if final_decision:
                    rc.final_decision = final_decision
                if data["primary_guardian"] and not rc.primary_guardian:
                    rc.primary_guardian = data["primary_guardian"]
                rc.save(ignore_permissions=True)
                updated.append(row.student)
            else:
                rc = frappe.new_doc("Report Card")
                rc.student = row.student
                rc.academic_year = doc.academic_year
                rc.school_class = doc.school_class
                rc.class_group = doc.class_group
                rc.primary_guardian = data["primary_guardian"]
                rc.final_decision = final_decision
                for r in data["rows"]:
                    rc.append("report_card_rows", r)
                rc.insert(ignore_permissions=False)
                created.append(rc.name)

        except Exception:
            frappe.log_error(
                title=f"Escola — falha ao criar/actualizar Boletim para {row.student}",
                message=frappe.get_traceback(),
            )
            errors.append(row.student)

    return {"created": created, "updated": updated, "errors": errors}


@frappe.whitelist()
def sync_academic_closure_students(doc_name):
    """Remove rows for students whose current_status is not 'Activo'. Preserves decisions."""
    doc = frappe.get_doc("Academic Closure", doc_name)
    if not doc.closure_rows:
        return {"removed": 0, "kept": 0}

    students = [row.student for row in doc.closure_rows]
    active = set(
        frappe.get_all(
            "Student",
            filters={"name": ("in", students), "current_status": "Activo"},
            pluck="name",
        )
    )

    original = len(doc.closure_rows)
    kept = [r for r in doc.closure_rows if r.student in active]
    removed = original - len(kept)

    if removed:
        doc.set("closure_rows", kept)
        doc.save(ignore_permissions=True)

    return {"removed": removed, "kept": len(kept)}
