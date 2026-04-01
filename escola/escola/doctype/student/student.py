import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, today


@frappe.whitelist()
def get_student_academic_history(student):
    """Return academic history aggregated per academic year for the given student."""
    from collections import defaultdict

    # 1. Student Group Assignments → backbone (one slot per unique academic_year, most recent SGA wins)
    sgas = frappe.db.get_all(
        "Student Group Assignment",
        filters={"student": student},
        fields=["academic_year", "class_group", "school_class", "status", "assignment_date"],
        order_by="academic_year desc, assignment_date desc",
    )

    years = {}
    for sga in sgas:
        yr = sga.academic_year or "—"
        if yr not in years:
            years[yr] = {
                "academic_year": yr,
                "school_class": sga.school_class or "",
                "class_group": sga.class_group or "",
                "sga_status": sga.status or "",
                "assignment_date": frappe.utils.formatdate(sga.assignment_date) if sga.assignment_date else "",
                "final_decision": "",
                "overall_average": None,
                "total_absences": None,
                "report_card": None,
            }

    # 2. Report Cards → enrich with overall_average, final_decision, name
    rcs = frappe.db.get_all(
        "Report Card",
        filters={"student": student},
        fields=["name", "academic_year", "overall_average", "final_decision"],
    )
    for rc in rcs:
        yr = rc.academic_year or "—"
        if yr not in years:
            years[yr] = {
                "academic_year": yr,
                "school_class": "",
                "class_group": "",
                "sga_status": "",
                "assignment_date": "",
                "final_decision": "",
                "overall_average": None,
                "total_absences": None,
                "report_card": None,
            }
        years[yr]["report_card"] = rc.name
        years[yr]["final_decision"] = rc.final_decision or ""
        if rc.overall_average is not None:
            years[yr]["overall_average"] = float(rc.overall_average)

    # 3. Total absences from Annual Assessment Rows
    aa_rows = frappe.db.sql(
        """
        SELECT aa.academic_year, SUM(aar.total_absences) AS total_absences
        FROM `tabAnnual Assessment Row` aar
        JOIN `tabAnnual Assessment` aa ON aa.name = aar.parent
        WHERE aar.student = %s
        GROUP BY aa.academic_year
        """,
        student,
        as_dict=True,
    )
    for row in aa_rows:
        yr = row.academic_year or "—"
        if yr in years:
            years[yr]["total_absences"] = int(row.total_absences or 0)

    # 4. Fallback absences from Term Attendance Rows (years not already covered)
    missing = [yr for yr, d in years.items() if d["total_absences"] is None]
    if missing:
        ta_rows = frappe.db.sql(
            """
            SELECT ta.academic_year, SUM(tar.total_absences) AS total_absences
            FROM `tabTerm Attendance Row` tar
            JOIN `tabTerm Attendance` ta ON ta.name = tar.parent
            WHERE tar.student = %s
            GROUP BY ta.academic_year
            """,
            student,
            as_dict=True,
        )
        for row in ta_rows:
            yr = row.academic_year or "—"
            if yr in years and years[yr]["total_absences"] is None:
                years[yr]["total_absences"] = int(row.total_absences or 0)

    return sorted(years.values(), key=lambda x: x["academic_year"], reverse=True)


def _calc_age(date_of_birth):
    if not date_of_birth:
        return None
    dob = getdate(date_of_birth)
    tod = getdate(today())
    age = tod.year - dob.year - ((tod.month, tod.day) < (dob.month, dob.day))
    return age if age >= 0 else None


def update_all_student_ages():
    """Daily scheduler job — recalculates idade for every student with a date_of_birth."""
    rows = frappe.db.get_all(
        "Student",
        filters=[["date_of_birth", "is", "set"]],
        fields=["name", "date_of_birth"],
    )
    for row in rows:
        age = _calc_age(row.date_of_birth)
        if age is not None:
            frappe.db.set_value("Student", row.name, "idade", age, update_modified=False)
    if rows:
        frappe.db.commit()


class Student(Document):
    def before_insert(self):
        self._sync_full_name()
        self._generate_student_code()

    def after_insert(self):
        try:
            ensure_customer_for_student(self.name)
        except Exception:
            pass  # never block student creation

    def before_save(self):
        self._sync_full_name()
        self.idade = _calc_age(self.date_of_birth)
        if not self.current_status:
            self.current_status = "Activo"

    def _sync_full_name(self):
        parts = filter(None, [self.first_name, self.last_name])
        self.full_name = " ".join(parts)

    def _generate_student_code(self):
        if self.student_code:
            return
        last = frappe.db.sql(
            "SELECT student_code FROM `tabStudent` "
            "WHERE student_code LIKE 'ALU-%' "
            "ORDER BY student_code DESC LIMIT 1"
        )
        if last and last[0][0]:
            try:
                seq = int(last[0][0].split("-")[1]) + 1
            except (IndexError, ValueError):
                seq = 1
        else:
            seq = 1
        self.student_code = "ALU-{:05d}".format(seq)


# ---------------------------------------------------------------------------
# Customer provisioning
# ---------------------------------------------------------------------------

def ensure_customer_for_student(student_name):
    """
    Return the ERPNext Customer linked to this student, creating one if needed.
    Safe to call multiple times — never creates duplicates.
    """
    try:
        existing = frappe.db.get_value("Customer", {"escola_student": student_name}, "name")
        if existing:
            return existing
    except Exception:
        pass

    student = (
        frappe.db.get_value("Student", student_name, ["full_name", "student_code"], as_dict=True)
        or frappe._dict()
    )
    full_name = student.get("full_name") or student_name

    customer = frappe.new_doc("Customer")
    customer.customer_name = full_name
    customer.customer_type = "Individual"
    customer.customer_group = (
        frappe.db.get_single_value("School Settings", "default_customer_group")
        or frappe.db.get_single_value("Selling Settings", "customer_group")
        or "All Customer Groups"
    )
    customer.territory = (
        frappe.db.get_single_value("School Settings", "default_territory")
        or frappe.db.get_single_value("Selling Settings", "territory")
        or "All Territories"
    )

    try:
        customer.escola_student = student_name
    except Exception:
        pass

    customer.insert(ignore_permissions=True)
    return customer.name
