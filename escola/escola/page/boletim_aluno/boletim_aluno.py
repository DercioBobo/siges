import frappe
from frappe import _


@frappe.whitelist()
def get_student_report(student, academic_year=None):
    """
    Consolidated academic report for a student.
    Reads directly from Grade Entry and Student Promotion — no Report Card dependency.
    """
    student_doc = frappe.db.get_value(
        "Student", student,
        ["full_name", "student_code", "current_status"],
        as_dict=True,
    )
    if not student_doc:
        return {"error": "student_not_found"}

    sga_filters = {"student": student}
    if academic_year:
        sga_filters["academic_year"] = academic_year

    sgas = frappe.get_all(
        "Student Group Assignment",
        filters=sga_filters,
        fields=["academic_year", "school_class", "class_group", "status"],
        order_by="academic_year desc",
    )

    years = []
    for sga in sgas:
        y = _build_year(student, sga)
        if y:
            years.append(y)

    return {
        "student":        student,
        "full_name":      student_doc.full_name,
        "student_code":   student_doc.student_code,
        "current_status": student_doc.current_status,
        "years":          years,
    }


def _build_year(student, sga):
    year = sga.academic_year

    terms = frappe.get_all(
        "Academic Term",
        filters={"academic_year": year},
        fields=["name", "term_name", "start_date"],
        order_by="start_date asc",
    )
    if not terms:
        return None

    term_names = [t.name for t in terms]
    ph = ", ".join(["%s"] * len(term_names))

    rows = frappe.db.sql(
        f"""
        SELECT ge.academic_term, ger.subject, AVG(ger.score) AS avg_score
        FROM `tabGrade Entry Row` ger
        JOIN `tabGrade Entry` ge ON ge.name = ger.parent
        WHERE ger.student = %s
          AND ge.academic_year = %s
          AND ge.academic_term IN ({ph})
          AND ge.docstatus != 2
          AND ger.is_absent = 0
          AND ger.score IS NOT NULL
        GROUP BY ge.academic_term, ger.subject
        ORDER BY ger.subject
        """,
        [student, year] + term_names,
        as_dict=True,
    )

    if not rows:
        return None

    # subject → term → average score
    sm = {}
    for r in rows:
        sm.setdefault(r.subject, {})[r.academic_term] = round(float(r.avg_score), 1)

    subjects = []
    for subj in sorted(sm):
        term_grades = [sm[subj].get(t.name) for t in terms]
        valid = [g for g in term_grades if g is not None]
        annual = round(sum(valid) / len(valid), 1) if valid else None
        subjects.append({
            "subject":        subj,
            "term_grades":    term_grades,
            "annual_average": annual,
        })

    # per-term class average
    term_averages = []
    for i in range(len(terms)):
        vals = [s["term_grades"][i] for s in subjects if s["term_grades"][i] is not None]
        term_averages.append(round(sum(vals) / len(vals), 1) if vals else None)

    # overall annual average
    ann_vals = [s["annual_average"] for s in subjects if s["annual_average"] is not None]
    overall = round(sum(ann_vals) / len(ann_vals), 1) if ann_vals else None

    return {
        "academic_year":   year,
        "school_class":    sga.school_class,
        "class_group":     sga.class_group,
        "sga_status":      sga.status,
        "term_labels":     [t.term_name or t.name for t in terms],
        "subjects":        subjects,
        "term_averages":   term_averages,
        "overall_average": overall,
        "final_decision":  _get_final_decision(student, sga),
        "total_absences":  _get_absences(student, sga),
    }


def _get_final_decision(student, sga):
    # Student Promotion is most authoritative
    promotion = frappe.db.get_value(
        "Student Promotion",
        {"academic_year": sga.academic_year, "class_group": sga.class_group},
        "name",
    )
    if promotion:
        d = frappe.db.get_value(
            "Student Promotion Row",
            {"parent": promotion, "student": student},
            "decision",
        )
        if d:
            return d

    # Fall back to Annual Assessment result
    ann = frappe.db.get_value(
        "Annual Assessment",
        {"academic_year": sga.academic_year, "class_group": sga.class_group},
        "name",
    )
    if ann:
        result = frappe.db.get_value(
            "Annual Assessment Row",
            {"parent": ann, "student": student},
            "result",
        )
        if result == "Aprovado":
            return "Promovido"
        if result == "Reprovado":
            return "Retido"

    return None


def _get_absences(student, sga):
    ann = frappe.db.get_value(
        "Annual Assessment",
        {"academic_year": sga.academic_year, "class_group": sga.class_group},
        "name",
    )
    if not ann:
        return None
    val = frappe.db.get_value(
        "Annual Assessment Row",
        {"parent": ann, "student": student},
        "total_absences",
    )
    return int(val) if val is not None else None
