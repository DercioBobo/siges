import frappe
from frappe import _


def execute(filters=None):
    filters = filters or {}

    columns = [
        {
            "label": _("Aluno"),
            "fieldname": "student",
            "fieldtype": "Link",
            "options": "Student",
            "width": 130,
        },
        {
            "label": _("Nome Completo"),
            "fieldname": "full_name",
            "fieldtype": "Data",
            "width": 210,
        },
        {
            "label": _("Total Dias"),
            "fieldname": "total_days",
            "fieldtype": "Int",
            "width": 90,
        },
        {
            "label": _("Presente"),
            "fieldname": "present",
            "fieldtype": "Int",
            "width": 90,
        },
        {
            "label": _("Ausente"),
            "fieldname": "absent",
            "fieldtype": "Int",
            "width": 90,
        },
        {
            "label": _("Atrasado"),
            "fieldname": "late",
            "fieldtype": "Int",
            "width": 90,
        },
        {
            "label": _("Justificado"),
            "fieldname": "justified",
            "fieldtype": "Int",
            "width": 90,
        },
        {
            "label": _("% Presença"),
            "fieldname": "attendance_rate",
            "fieldtype": "Float",
            "width": 100,
            "precision": 1,
        },
    ]

    if not filters.get("class_group"):
        return columns, []

    conditions = ["sa.class_group = %(class_group)s"]
    if filters.get("academic_year"):
        conditions.append("sa.academic_year = %(academic_year)s")

    where = " AND ".join(conditions)

    data = frappe.db.sql(
        f"""
        SELECT
            sae.student,
            s.full_name,
            COUNT(*)                                                           AS total_days,
            SUM(sae.attendance_status = 'Presente')                           AS present,
            SUM(sae.attendance_status = 'Ausente')                            AS absent,
            SUM(sae.attendance_status = 'Atrasado')                           AS late,
            SUM(sae.attendance_status = 'Justificado')                        AS justified,
            ROUND(
                SUM(sae.attendance_status = 'Presente') * 100.0 / COUNT(*), 1
            )                                                                  AS attendance_rate
        FROM `tabStudent Attendance Entry` sae
        INNER JOIN `tabStudent Attendance` sa  ON sa.name  = sae.parent
        INNER JOIN `tabStudent`            s   ON s.name   = sae.student
        WHERE {where}
        GROUP BY sae.student, s.full_name
        ORDER BY s.full_name
        """,
        filters,
        as_dict=True,
    )

    return columns, data
