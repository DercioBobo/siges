import math
import frappe
from frappe import _
from frappe.model.document import Document
from escola.escola.doctype.term_attendance.term_attendance import get_annual_absences


@frappe.whitelist()
def get_students_for_assessment(class_group):
    """Return active students in a class group."""
    sgas = frappe.db.get_all(
        "Student Group Assignment",
        filters={"class_group": class_group, "status": "Activa"},
        fields=["student"],
        order_by="student asc",
    )
    return [s.student for s in sgas]


@frappe.whitelist()
def calculate_assessment(doc_name):
    """
    Compute per-student overall averages from Grade Entry data.

    Returns:
        {
            "rows":    [ {student, term_1_average, term_2_average, term_3_average,
                          final_grade, total_absences, result}, ... ],
            "details": { student: { subject: {t1, t2, t3, avg}, ... }, ... },
            "terms":   ["T1", "T2", "T3"]   (labels of present terms)
        }
    """
    doc = frappe.get_doc("Annual Assessment", doc_name)

    terms = frappe.get_all(
        "Academic Term",
        filters={"academic_year": doc.academic_year},
        fields=["name", "term_name", "start_date"],
        order_by="start_date asc, name asc",
    )
    if not terms:
        return {"error": "no_terms"}

    # Position map: term_name → 1/2/3
    term_position = {t.name: idx + 1 for idx, t in enumerate(terms)}
    term_labels   = [t.term_name or t.name for t in terms]

    min_passing = float(
        frappe.db.get_value("School Class", doc.school_class, "minimum_passing_grade")
        or frappe.db.get_single_value("School Settings", "minimum_passing_grade")
        or 10
    )

    grade_entries = frappe.get_all(
        "Grade Entry",
        filters={
            "class_group": doc.class_group,
            "academic_year": doc.academic_year,
            "docstatus": ("!=", 2),
        },
        fields=["name", "academic_term", "subject"],
    )
    if not grade_entries:
        return {"error": "no_grade_entries"}

    # data[student][subject][term_pos] = [mt, ...]
    data: dict = {}
    for entry in grade_entries:
        pos = term_position.get(entry.academic_term)
        if pos is None:
            continue
        rows = frappe.get_all(
            "Grade Entry Row",
            filters={"parent": entry.name, "is_absent": 0},
            fields=["student", "mt"],
        )
        for row in rows:
            if row.mt is None:
                continue
            (
                data
                .setdefault(row.student, {})
                .setdefault(entry.subject, {})
                .setdefault(pos, [])
                .append(float(row.mt))
            )

    if not data:
        return {"error": "no_grades"}

    absences = get_annual_absences(doc.class_group, doc.academic_year)
    comportamentos = _compute_annual_comportamento(doc.class_group, doc.academic_year)
    abs_threshold = int(
        frappe.db.get_single_value("School Settings", "max_absences_threshold") or 0
    )
    max_terms = len(terms)

    result_rows = []
    details = {}

    for student in sorted(data):
        student_abs = absences.get(student, {})
        total_abs   = student_abs.get("total", 0)

        # Per subject: average per term
        subject_term_avgs = {}  # subject → {pos: avg}
        for subject, term_scores in data[student].items():
            subject_term_avgs[subject] = {
                pos: round(sum(vals) / len(vals), 2)
                for pos, vals in term_scores.items()
            }

        # Per term: mean of all subject averages
        term_avgs = {}  # pos → mean across subjects
        for pos in range(1, max_terms + 1):
            vals = [
                subject_term_avgs[subj][pos]
                for subj in subject_term_avgs
                if pos in subject_term_avgs[subj]
            ]
            if vals:
                term_avgs[pos] = round(sum(vals) / len(vals), 2)

        all_term_avgs = list(term_avgs.values())
        final_grade   = round(sum(all_term_avgs) / len(all_term_avgs), 2) if all_term_avgs else 0.0
        result        = "Aprovado" if final_grade >= min_passing else "Reprovado"

        result_rows.append({
            "student":            student,
            "term_1_average":     term_avgs.get(1),
            "term_2_average":     term_avgs.get(2) if max_terms >= 2 else None,
            "term_3_average":     term_avgs.get(3) if max_terms >= 3 else None,
            "final_grade":        final_grade,
            "total_absences":     total_abs,
            "result":             result,
            "comportamento_anual": comportamentos.get(student),
        })

        # Details for HTML: subject → {t1, t2, t3, avg}
        subject_details = {}
        for subject, term_avgs_s in subject_term_avgs.items():
            s_avgs = list(term_avgs_s.values())
            subject_details[subject] = {
                "t1":  term_avgs_s.get(1),
                "t2":  term_avgs_s.get(2),
                "t3":  term_avgs_s.get(3),
                "avg": round(sum(s_avgs) / len(s_avgs), 2) if s_avgs else None,
            }
        details[student] = subject_details

    return {"rows": result_rows, "details": details, "terms": term_labels}


@frappe.whitelist()
def get_student_assessment_detail(doc_name, student):
    """Return subject-level assessment detail for a single student."""
    result = calculate_assessment(doc_name)
    if result.get("error"):
        return result
    return {
        "detail": result.get("details", {}).get(student),
        "row": next((r for r in result.get("rows", []) if r["student"] == student), None),
        "terms": result.get("terms"),
    }


class AnnualAssessment(Document):
    def validate(self):
        self._validate_class_group_compatibility()
        self._validate_uniqueness()
        self._validate_row_integrity()

    def _validate_class_group_compatibility(self):
        if not self.class_group:
            return
        cg = frappe.db.get_value(
            "Class Group",
            self.class_group,
            ["academic_year", "school_class"],
            as_dict=True,
        )
        if not cg:
            return
        if cg.academic_year != self.academic_year:
            frappe.throw(
                _("A Turma <b>{0}</b> pertence ao Ano Lectivo <b>{1}</b>, "
                  "não ao Ano Lectivo <b>{2}</b>.").format(
                    self.class_group, cg.academic_year, self.academic_year
                ),
                title=_("Turma incompatível"),
            )
        if self.school_class and cg.school_class != self.school_class:
            frappe.throw(
                _("A Turma <b>{0}</b> pertence à Classe <b>{1}</b>, "
                  "não à Classe <b>{2}</b>.").format(
                    self.class_group, cg.school_class, self.school_class
                ),
                title=_("Classe incompatível"),
            )

    def _validate_uniqueness(self):
        existing = frappe.db.get_value(
            "Annual Assessment",
            {
                "academic_year": self.academic_year,
                "class_group":   self.class_group,
                "name":          ("!=", self.name),
            },
            "name",
        )
        if existing:
            frappe.throw(
                _("Já existe uma Avaliação Anual para a Turma <b>{0}</b> "
                  "no Ano Lectivo <b>{1}</b>: <b>{2}</b>.").format(
                    self.class_group, self.academic_year, existing
                ),
                title=_("Avaliação duplicada"),
            )

    def _validate_row_integrity(self):
        max_grade = float(
            frappe.db.get_single_value("School Settings", "grading_scale_max") or 20
        )
        seen = set()
        for row in self.assessment_rows:
            if row.final_grade is not None and (
                row.final_grade < 0 or row.final_grade > max_grade
            ):
                frappe.throw(
                    _("A média geral <b>{0}</b> para o aluno <b>{1}</b> "
                      "está fora do intervalo 0–{2}.").format(
                        row.final_grade, row.student, max_grade
                    ),
                    title=_("Nota fora do intervalo"),
                )
            if row.student in seen:
                frappe.throw(
                    _("O aluno <b>{0}</b> aparece mais de uma vez na tabela.").format(
                        row.student
                    ),
                    title=_("Aluno duplicado"),
                )
            seen.add(row.student)


def _compute_annual_comportamento(class_group, academic_year):
    """Average comportamento weights per student across all terms, apply ceiling, return {student: label}."""
    records = frappe.get_all(
        "Term Attendance",
        filters={"class_group": class_group, "academic_year": academic_year, "docstatus": ("!=", 2)},
        fields=["name"],
    )
    if not records:
        return {}

    ta_names = [r.name for r in records]
    placeholders = ", ".join(["%s"] * len(ta_names))
    rows = frappe.db.sql(
        f"SELECT student, comportamento FROM `tabTerm Attendance Row` "
        f"WHERE parent IN ({placeholders}) AND comportamento IS NOT NULL AND comportamento != ''",
        ta_names,
        as_dict=True,
    )
    if not rows:
        return {}

    options = frappe.get_all(
        "Behaviour Option",
        filters={"is_active": 1},
        fields=["name", "weight"],
        order_by="weight asc",
    )
    if not options:
        return {}

    weight_map = {o.name: int(o.weight or 0) for o in options}

    student_weights = {}
    for row in rows:
        w = weight_map.get(row.comportamento)
        if w is not None:
            student_weights.setdefault(row.student, []).append(w)

    result = {}
    for student, weights in student_weights.items():
        ceil_val = math.ceil(sum(weights) / len(weights))
        match = next((o.name for o in options if int(o.weight or 0) == ceil_val), None)
        if not match:
            match = next((o.name for o in options if int(o.weight or 0) >= ceil_val), None)
        if not match:
            match = options[-1].name
        result[student] = match

    return result


@frappe.whitelist()
def get_mapa_print_data(doc_name):
    """Return full grade matrix for Mapa de Aproveitamento print view."""
    doc = frappe.get_doc("Annual Assessment", doc_name)

    terms = frappe.get_all(
        "Academic Term",
        filters={"academic_year": doc.academic_year},
        fields=["name", "term_name", "start_date"],
        order_by="start_date asc",
    )

    # Subjects from School Class
    subjects = []
    school_class = frappe.db.get_value("Class Group", doc.class_group, "school_class")
    if school_class:
        lines = frappe.get_all(
            "School Class Subject",
            filters={"parent": school_class},
            fields=["subject"],
            order_by="idx asc",
        )
        sn_list = [l.subject for l in lines if l.subject]
        subj_map = {
            s.name: s.subject_name
            for s in frappe.get_all(
                "Subject",
                filters={"name": ("in", sn_list)},
                fields=["name", "subject_name"],
            )
        }
        subjects = [{"name": sn, "label": subj_map.get(sn, sn)} for sn in sn_list if sn in subj_map]

    # MT data: student → subject → term_pos → mt
    grade_data: dict = {}
    for i, term in enumerate(terms):
        pos = i + 1
        ges = frappe.get_all(
            "Grade Entry",
            filters={
                "class_group": doc.class_group,
                "academic_term": term.name,
                "docstatus": ("!=", 2),
            },
            fields=["name", "subject"],
        )
        for ge in ges:
            ge_rows = frappe.get_all(
                "Grade Entry Row",
                filters={"parent": ge.name, "is_absent": 0},
                fields=["student", "mt"],
            )
            for row in ge_rows:
                if row.mt is not None:
                    grade_data.setdefault(row.student, {}).setdefault(ge.subject, {})[pos] = float(row.mt)

    # Build student rows
    assessment_map = {r.student: r for r in doc.assessment_rows}
    students = frappe.db.sql(
        """
        SELECT sga.student, s.full_name AS student_name, s.student_code
        FROM `tabStudent Group Assignment` sga
        JOIN `tabStudent` s ON s.name = sga.student
        WHERE sga.class_group = %s AND sga.academic_year = %s AND sga.status = 'Activa'
        ORDER BY s.full_name
        """,
        (doc.class_group, doc.academic_year),
        as_dict=True,
    )

    student_rows = []
    for idx, s in enumerate(students):
        sd = grade_data.get(s.student, {})
        subj_data = {}
        for subj in subjects:
            td = sd.get(subj["name"], {})
            vals = [td.get(p) for p in range(1, len(terms) + 1)]
            valid = [v for v in vals if v is not None]
            subj_data[subj["name"]] = {
                "terms": vals,
                "af": round(sum(valid) / len(valid), 2) if valid else None,
            }

        # Per-term class-wide averages
        term_avgs = []
        for p in range(1, len(terms) + 1):
            vals = [sd.get(subj["name"], {}).get(p) for subj in subjects]
            valid = [v for v in vals if v is not None]
            term_avgs.append(round(sum(valid) / len(valid), 2) if valid else None)

        valid_ta = [v for v in term_avgs if v is not None]
        final_grade = round(sum(valid_ta) / len(valid_ta), 2) if valid_ta else None

        ar = assessment_map.get(s.student)
        student_rows.append({
            "idx": idx + 1,
            "student": s.student,
            "student_name": s.student_name,
            "subject_data": subj_data,
            "term_averages": term_avgs,
            "final_grade": final_grade,
            "result": ar.result if ar else None,
            "total_absences": ar.total_absences if ar else None,
            "comportamento": ar.comportamento_anual if ar else None,
        })

    # School / class info
    school_name = frappe.db.get_single_value("School Settings", "school_name") or ""
    cg_info = frappe.db.get_value(
        "Class Group", doc.class_group,
        ["group_name", "class_teacher"],
        as_dict=True,
    ) or {}
    teacher_name = ""
    if cg_info.get("class_teacher"):
        teacher_name = frappe.db.get_value("Teacher", cg_info.class_teacher, "full_name") or cg_info.class_teacher

    return {
        "school_name": school_name,
        "class_group_name": cg_info.get("group_name") or doc.class_group,
        "teacher_name": teacher_name,
        "academic_year": doc.academic_year,
        "terms": [{"name": t.name, "label": t.term_name or t.name} for t in terms],
        "subjects": subjects,
        "rows": student_rows,
    }


@frappe.whitelist()
def sync_annual_assessment_students(doc_name):
    """Remove rows for students whose current_status is not 'Activo'. Preserves grades."""
    doc = frappe.get_doc("Annual Assessment", doc_name)
    if not doc.assessment_rows:
        return {"removed": 0, "kept": 0}

    students = [row.student for row in doc.assessment_rows]
    active = set(
        frappe.get_all(
            "Student",
            filters={"name": ("in", students), "current_status": "Activo"},
            pluck="name",
        )
    )

    original = len(doc.assessment_rows)
    kept = [r for r in doc.assessment_rows if r.student in active]
    removed = original - len(kept)

    if removed:
        doc.set("assessment_rows", kept)
        doc.save(ignore_permissions=True)

    return {"removed": removed, "kept": len(kept)}
