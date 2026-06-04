import frappe
from frappe import _
from frappe.model.document import Document


class AberturadeAnoLectivo(Document):
    def validate(self):
        if self.source_academic_year == self.target_academic_year:
            frappe.throw(
                _("O Novo Ano Lectivo não pode ser igual ao Ano Actual."),
                title=_("Anos inválidos"),
            )
        # Block if another submitted opening already targets this year
        existing = frappe.db.get_value(
            "Abertura de Ano Lectivo",
            {"target_academic_year": self.target_academic_year, "docstatus": 1, "name": ("!=", self.name)},
            "name",
        )
        if existing:
            frappe.throw(
                _("Já existe uma Abertura de Ano Lectivo submetida para <b>{0}</b>: <b>{1}</b>.").format(
                    self.target_academic_year, existing
                ),
                title=_("Ano já aberto"),
            )

    def on_submit(self):
        self._check_target_has_class_groups()
        self._set_school_settings()
        self._flag_pending_students()
        self.db_set("status", "Concluída")

    # ------------------------------------------------------------------

    def _check_target_has_class_groups(self):
        count = frappe.db.count(
            "Class Group",
            {"academic_year": self.target_academic_year, "is_active": 1},
        )
        if not count:
            frappe.throw(
                _("Não existem Turmas activas para o Ano Lectivo <b>{0}</b>. "
                  "Crie as turmas do novo ano antes de abrir o ano lectivo.").format(
                    self.target_academic_year
                ),
                title=_("Turmas em falta"),
            )

    def _set_school_settings(self):
        frappe.db.set_single_value(
            "School Settings", "current_academic_year", self.target_academic_year
        )

    def _flag_pending_students(self):
        """Students active in the source year without any SGA in target year → Pendente de Renovação."""
        active_in_source = frappe.db.get_all(
            "Student Group Assignment",
            filters={"academic_year": self.source_academic_year, "status": "Activa"},
            pluck="student",
        )
        if not active_in_source:
            return

        already_in_target = set(frappe.db.get_all(
            "Student Group Assignment",
            filters={"academic_year": self.target_academic_year},
            pluck="student",
        ))

        to_flag = [s for s in active_in_source if s not in already_in_target]
        for student in to_flag:
            frappe.db.set_value(
                "Student", student, "current_status", "Pendente de Renovação",
                update_modified=False,
            )


# ------------------------------------------------------------------
# Whitelisted helpers
# ------------------------------------------------------------------

@frappe.whitelist()
def get_preflight_data(source_academic_year, target_academic_year):
    """
    Returns a preflight summary for the year-opening wizard:
    - class groups in target year
    - promotions done vs pending
    - students that will be flagged Pendente de Renovação
    """
    # Class groups in target year
    target_groups = frappe.db.get_all(
        "Class Group",
        filters={"academic_year": target_academic_year, "is_active": 1},
        fields=["name", "group_name", "student_count"],
        order_by="group_name asc",
    )

    # Student Promotions submitted for source year
    promotions_done = frappe.db.get_all(
        "Student Promotion",
        filters={"academic_year": source_academic_year, "docstatus": 1},
        fields=["name", "class_group", "school_class"],
        order_by="class_group asc",
    )

    # Class Groups in source year that have NO submitted Student Promotion
    source_groups = frappe.db.get_all(
        "Class Group",
        filters={"academic_year": source_academic_year, "is_active": 1},
        fields=["name", "group_name", "school_class"],
        order_by="group_name asc",
    )
    promoted_groups = {p.class_group for p in promotions_done}
    promotions_missing = [g for g in source_groups if g.name not in promoted_groups]

    # Students active in source year
    active_in_source = frappe.db.get_all(
        "Student Group Assignment",
        filters={"academic_year": source_academic_year, "status": "Activa"},
        pluck="student",
    )
    already_in_target = set(frappe.db.get_all(
        "Student Group Assignment",
        filters={"academic_year": target_academic_year},
        pluck="student",
    ))
    pending_count = len([s for s in active_in_source if s not in already_in_target])
    promoted_count = len([s for s in active_in_source if s in already_in_target])

    return {
        "target_groups": target_groups,
        "promotions_done": promotions_done,
        "promotions_missing": promotions_missing,
        "students_total": len(active_in_source),
        "students_promoted": promoted_count,
        "students_pending": pending_count,
    }
