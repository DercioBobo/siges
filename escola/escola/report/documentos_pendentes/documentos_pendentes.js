frappe.query_reports["Documentos Pendentes"] = {
	filters: [
		{
			fieldname: "school_class",
			label: __("Classe"),
			fieldtype: "Link",
			options: "School Class",
		},
		{
			fieldname: "class_group",
			label: __("Turma"),
			fieldtype: "Link",
			options: "Class Group",
		},
		{
			fieldname: "required_only",
			label: __("Apenas Obrigatórios"),
			fieldtype: "Check",
			default: 1,
		},
	],
};
