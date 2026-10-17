from frappe import _


def get_data():
    """Connections tab on the Student form."""
    return {
        # Most doctypes link through a field called `student`; Sales Invoice
        # uses the escola_student custom field (see setup.py).
        "fieldname": "student",
        "non_standard_fieldnames": {
            "Sales Invoice": "escola_student",
        },
        "transactions": [
            {
                "label": _("Financeiro"),
                "items": ["Sales Invoice", "Adiantamento De Pagamento", "Mensalidade Extra do Aluno"],
            },
            {
                "label": _("Matrícula"),
                "items": ["Inscricao", "Renovacao De Matricula", "Student Group Assignment"],
            },
            {
                "label": _("Movimentos"),
                "items": ["Troca De Turma", "Student Transfer"],
            },
            {
                "label": _("Avaliação"),
                "items": ["Report Card"],
            },
        ],
    }
