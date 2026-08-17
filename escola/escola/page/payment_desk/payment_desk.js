frappe.pages["payment-desk"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Central de Pagamentos"),
		single_column: true,
	});

	const board = new escola.utils.InvoiceBoard(page, {
		query_module: "escola.escola.invoice_query",
		default_statuses: ["Em Aberto"],
		row_action_html: (row) => {
			// A draft's outstanding_amount is 0/unset before submission, so a
			// payable draft is judged by grand_total instead.
			const payable = row.docstatus === 0
				? flt(row.grand_total) > 0
				: (row.docstatus === 1 && flt(row.outstanding_amount) > 0);
			if (!payable) return `<span class="ibd-muted">—</span>`;
			return `<button type="button" class="btn btn-xs btn-primary ibd-pay-btn">${__("Pagar")}</button>`;
		},
		on_row_action_click: ($target, row) => {
			if (!$target.hasClass("ibd-pay-btn")) return;
			escola.utils.open_payment_dialog({
				invoice: row.invoice,
				docstatus: row.docstatus,
				default_amount: row.docstatus === 0 ? row.grand_total : row.outstanding_amount,
				penalty_amount: row.penalty_amount,
				on_success: () => board.search(),
			});
		},
	});

	page.add_button(__("Actualizar"), () => board.search(), { icon: "refresh" });
};
