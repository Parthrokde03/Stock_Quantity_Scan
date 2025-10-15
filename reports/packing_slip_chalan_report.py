# -*- coding: utf-8 -*-
from odoo import models

class ReportPackingSlip(models.AbstractModel):
    _name = "report.stock_quantity_scan.report_lot_barcodes_chalan_doc"
    _description = "Packing Slip (Static) - Normal Code128 barcode"

    def _get_report_values(self, docids, data=None):
        """
        Fetch quants and pass tare/net/gross weights to QWeb.
        """
        data = data or {}
        Quant = self.env['stock.quant'].sudo()

        # Retrieve quants either from data or product
        quant_ids = data.get('quant_ids') or []
        if quant_ids:
            quants = Quant.browse(quant_ids)
        elif self.env.context.get('active_model') == 'product.template':
            tmpl = self.env['product.template'].browse(self.env.context.get('active_id'))
            quants = Quant.search([
                ('product_id.product_tmpl_id', '=', tmpl.id),
                ('quantity', '>', 0),
            ], order="location_id, lot_id, id")
        else:
            quants = Quant.browse([])

        slips = []
        for idx, q in enumerate(quants, start=1):
            lot_name = (q.lot_id and q.lot_id.name) or 'NOLOT'
            box_no = f"{lot_name}"
            code = q.scan_barcode or box_no

            def format_weight(val):
                """Always return 1 decimal place for weights."""
                if val is None:
                    return "0.0"
                return f"{float(val):.1f}"

            def format_bobbin(val):
                """Remove .0 if integer."""
                if val is None:
                    return ""
                if float(val).is_integer():
                    return str(int(val))
                return str(val)

            gross_weight = (q.net_weight or 0) + (q.tare_weight or 0)

            slips.append({
                "box_no": box_no,
                "code": code,
                "quantity": format_bobbin(q.quantity),             # bobbin (no .0)
                "location": q.location_id.display_name,
                "net_weight": format_weight(q.net_weight),         # always decimal
                "tare_weight": format_weight(q.tare_weight),       # always decimal
                "gross_weight": format_weight(gross_weight),       # always decimal
                "product_name": q.product_id.name,     
            })


        return {
            "docs": self.env['product.template'].browse(docids),
            "slips": slips,
            "data": data,
        }
