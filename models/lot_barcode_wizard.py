# lot.py (wizard)

from odoo import api, fields, models, _
from odoo.exceptions import UserError

class LotBarcodeWizard(models.TransientModel):
    _name = "stock.lot.barcode.wizard"
    _description = "Print Lot Barcodes (Wizard)"

    product_tmpl_id = fields.Many2one(
        "product.template", string="Product", required=True, readonly=True
    )

    # NEW: lots that actually have on-hand quants in internal locations
    eligible_lot_ids = fields.Many2many(
        "stock.lot", compute="_compute_eligible_lots", string="Eligible Lots", readonly=True
    )

    lot_id = fields.Many2one(
        "stock.lot",
        string="Lot/Serial",
        domain="[('id', 'in', eligible_lot_ids)]",   # <— use only eligible lots
        help="Choose a single lot/serial to print. Leave empty to print all eligible lots.",
    )

    format = fields.Selection(
        [("barcode", "Barcode"), ("chalan", "Chalan")],
        string="Format", required=True, default="barcode",
    )

    @api.depends('product_tmpl_id')
    def _compute_eligible_lots(self):
        Quant = self.env['stock.quant'].sudo()
        for w in self:
            if not w.product_tmpl_id:
                w.eligible_lot_ids = [(6, 0, [])]
                continue
            # group by lot_id to avoid duplicates; only quants we can print
            rows = Quant.read_group(
                [
                    ('product_id.product_tmpl_id', '=', w.product_tmpl_id.id),
                    ('company_id', '=', self.env.company.id),
                    ('location_id.usage', '=', 'internal'),
                    ('quantity', '>', 0),
                    ('lot_id', '!=', False),
                ],
                fields=['lot_id'],
                groupby=['lot_id'],
            )
            lot_ids = [r['lot_id'][0] for r in rows if r.get('lot_id')]
            w.eligible_lot_ids = [(6, 0, lot_ids)]


    def _find_quants(self):
        """Return the quants to print, matching 'Update Quantity' logic and
        excluding 'No Lot' rows by default."""
        self.ensure_one()
        Quant = self.env["stock.quant"].sudo()

        domain = [
            ("product_id.product_tmpl_id", "=", self.product_tmpl_id.id),
            ("quantity", ">", 0),
            ("location_id.usage", "=", "internal"),
            ("company_id", "=", self.env.company.id),
        ]
        if self.lot_id:
            # single selected lot
            domain.append(("lot_id", "=", self.lot_id.id))
        else:
            # when printing “all”, skip quants without a lot
            domain.append(("lot_id", "!=", False))

        quants = Quant.search(domain, order="location_id, lot_id, id")
        if not quants:
            raise UserError(_("No internal quants with on-hand quantity for this selection."))

        # ensure each quant has barcode
        for q in quants:
            if not q.scan_barcode:
                q.scan_barcode = q._seq().next_by_id()
        return quants

    def action_print(self):
        self.ensure_one()
        quants = self._find_quants()

        xmlid = (
            "stock_quantity_scan.report_lot_barcodes_barcode_action"
            if self.format == "barcode"
            else "stock_quantity_scan.report_lot_barcodes_chalan_action"
        )
        action = self.env.ref(xmlid)
        # pass the product as docids and the quant ids in data
        return action.report_action(self.product_tmpl_id, data={"quant_ids": quants.ids})
