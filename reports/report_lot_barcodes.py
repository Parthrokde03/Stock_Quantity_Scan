# -*- coding: utf-8 -*-
from odoo import models

class ReportLotBarcodes(models.AbstractModel):
    _name = "report.stock_quantity_scan.report_lot_barcodes_doc"
    _description = "Lot Barcodes report (by product)"

    def _get_report_values(self, docids, data=None):
        """
        docids are product.template ids because the report action's model is product.template.
        We return both docs (products) and a dict of their quants.
        """
        products = self.env['product.template'].browse(docids)
        Quant = self.env['stock.quant'].sudo()

        quants_by_product = {}
        for p in products:
            quants_by_product[p.id] = Quant.search([
                ('product_id.product_tmpl_id', '=', p.id),
                ('quantity', '>', 0),
            ], order="location_id, lot_id, id")

        return {
            "docs": products,                   # what the template loops on
            "quants_by_product": quants_by_product,  # {product_id: quants}
            "data": data or {},
        }
