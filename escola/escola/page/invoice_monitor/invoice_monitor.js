frappe.pages["invoice-monitor"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Monitor de Facturas"),
		single_column: true,
	});

	const board = new escola.utils.InvoiceBoard(page, {
		query_module: "escola.escola.invoice_query",
		default_statuses: ["Em Aberto"],
		row_action_html: (row) =>
			`<a href="/app/sales-invoice/${row.invoice}" target="_blank" class="ibd-link" title="${__("Abrir factura")}">↗</a>`,
	});

	page.add_button(__("Actualizar"), () => board.search(), { icon: "refresh" });
};
