// Copyright (c) 2024, EntreTech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Assessment Scheme", {
	refresh(frm) {
		show_weight_total(frm);
	},
});

frappe.ui.form.on("Assessment Scheme Component", {
	weight(frm) {
		show_weight_total(frm);
	},
	components_remove(frm) {
		show_weight_total(frm);
	},
});

function show_weight_total(frm) {
	const total = (frm.doc.components || []).reduce(
		(sum, row) => sum + (row.weight || 0),
		0
	);
	const rounded = Math.round(total * 100) / 100;
	const colour = Math.abs(rounded - 100) < 0.01 ? "green" : "red";
	frm.dashboard.set_headline_alert(
		__("Soma dos pesos: <strong>{0}%</strong>", [rounded]),
		colour
	);
}
