import frappe
from frappe import _


def execute(filters=None):
    filters = filters or {}

    columns = [
        {
            "label": _("Turma"),
            "fieldname": "turma",
            "fieldtype": "Link",
            "options": "Class Group",
            "width": 150,
        },
        {
            "label": _("Classe"),
            "fieldname": "classe",
            "fieldtype": "Link",
            "options": "School Class",
            "width": 110,
        },
        {
            "label": _("Aluno"),
            "fieldname": "student",
            "fieldtype": "Link",
            "options": "Student",
            "width": 120,
        },
        {
            "label": _("Nome Completo"),
            "fieldname": "student_name",
            "fieldtype": "Data",
            "width": 220,
        },
        {
            "label": _("Estado"),
            "fieldname": "status",
            "fieldtype": "Data",
            "width": 120,
        },
        {
            "label": _("Data de Renovação"),
            "fieldname": "renewal_date",
            "fieldtype": "Date",
            "width": 130,
        },
        {
            "label": _("Ano de Renovação"),
            "fieldname": "target_academic_year",
            "fieldtype": "Link",
            "options": "Academic Year",
            "width": 130,
        },
        {
            "label": _("Renovação"),
            "fieldname": "renovacao",
            "fieldtype": "Link",
            "options": "Renovacao De Matricula",
            "width": 130,
        },
        {
            "label": _("Factura"),
            "fieldname": "sales_invoice",
            "fieldtype": "Link",
            "options": "Sales Invoice",
            "width": 130,
        },
    ]

    join_conditions = [
        "r.student = cgs.student",
        "r.academic_year = cg.academic_year",
        "r.docstatus != 2",  # exclude cancelled from the join so they show as Não Renovado
    ]
    if filters.get("target_academic_year"):
        join_conditions.append("r.target_academic_year = %(target_academic_year)s")

    where_conditions = ["1=1"]
    if filters.get("academic_year"):
        where_conditions.append("cg.academic_year = %(academic_year)s")
    if filters.get("class_group"):
        where_conditions.append("cg.name = %(class_group)s")
    if filters.get("status"):
        if filters["status"] == "Renovado":
            where_conditions.append("r.docstatus = 1")
        elif filters["status"] == "Não Renovado":
            where_conditions.append("r.name IS NULL")
        elif filters["status"] == "Rascunho":
            where_conditions.append("r.docstatus = 0")

    join_sql   = " AND ".join(join_conditions)
    where_sql  = " AND ".join(where_conditions)

    data = frappe.db.sql(
        f"""
        SELECT
            cg.name          AS class_group,
            cg.group_name    AS turma,
            cg.school_class  AS classe,
            cgs.student,
            cgs.student_name,
            CASE
                WHEN r.docstatus = 1 THEN 'Renovado'
                WHEN r.docstatus = 0 THEN 'Rascunho'
                ELSE 'Não Renovado'
            END              AS status,
            r.renewal_date,
            r.target_academic_year,
            r.name           AS renovacao,
            r.sales_invoice
        FROM `tabClass Group Student` cgs
        JOIN  `tabClass Group` cg
              ON cg.name = cgs.parent
        LEFT JOIN `tabRenovacao De Matricula` r
              ON {join_sql}
        WHERE {where_sql}
        ORDER BY cg.group_name ASC, cgs.student_name ASC
        """,
        filters,
        as_dict=True,
    )

    return columns, data
