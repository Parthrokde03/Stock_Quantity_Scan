# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError

class StockQuant(models.Model):
    _inherit = "stock.quant"

    scan_barcode = fields.Char(
        string="Quant Barcode",
        copy=False,
        index=True,
        help="Unique barcode for this quant (Location × Product × Lot).",
    )
    
    net_weight = fields.Float(
        string="Net Weight",
        help="Net weight of the package/product."
    )
    tare_weight = fields.Float(
        string="Tare Weight",
        help="Tare weight of the package/product."
    )

    _sql_constraints = [
        ("scan_barcode_unique", "unique(scan_barcode)", "Barcode must be unique per quant."),
    ]

    # -------------------- sequence helpers --------------------
    def _seq(self):
        return self.env.ref("stock_quantity_scan.seq_stock_quant_barcode")

    def _bump_sequence(self, seq, next_num):
        seq.sudo().write({'number_next': next_num})

    def _get_next_free_barcode(self, seq):
        prefix  = seq.prefix or ''
        padding = seq.padding or 0
        num = seq.number_next
        while True:
            code = f"{prefix}{str(num).zfill(padding)}"
            if not self.sudo().search_count([('scan_barcode', '=', code)]):
                return code, num
            num += 1

    # -------------------- when user clicks the button --------------------
    def action_generate_barcode(self):
        for q in self:
            if q.scan_barcode:
                raise UserError(_("This quant already has a barcode."))
            # only generate for “real/visible” quants
            if q.location_id.usage == 'internal' and q.lot_id and q.quantity > 0:
                seq = q._seq().sudo()
                code, num = q._get_next_free_barcode(seq)
                q.scan_barcode = code
                q._bump_sequence(seq, num + 1)
            else:
                raise UserError(_("Barcode is only generated for internal, positive quants with a lot."))
        return True

    # -------------------- create path --------------------
    @api.model_create_multi
    def create(self, vals_list):
        """
        Allow creating quants manually (bypassing Odoo's restriction).
        This uses low-level _create() to skip the base stock.quant.create() restriction.
        """
        for vals in vals_list:
            if not vals.get('product_id'):
                raise UserError(_("Please select a Product before creating a Quant."))
            if not vals.get('location_id'):
                raise UserError(_("Please select a Location before creating a Quant."))

        # ⚠️ Directly use _create() instead of super().create()
        # This bypasses Odoo's restriction message "Quant's creation is restricted"
        res = super(models.Model, self).create(vals_list)

        # 🪄 Auto-generate barcode if applicable
        for q in res:
            if (
                not q.scan_barcode
                and q.location_id.usage == 'internal'
                and q.lot_id
                and q.quantity > 0
            ):
                seq = q._seq().sudo()
                code, num = q._get_next_free_barcode(seq)
                q.scan_barcode = code
                q._bump_sequence(seq, num + 1)

        return res


    # (optional but useful) assign when a quant later becomes eligible
    def write(self, vals):
        res = super().write(vals)
        for q in self:
            if (
                not q.scan_barcode
                and q.location_id.usage == 'internal'
                and q.lot_id
                and q.quantity > 0
            ):
                seq = q._seq().sudo()
                code, num = q._get_next_free_barcode(seq)
                q.scan_barcode = code
                q._bump_sequence(seq, num + 1)
        return res



    def action_consume_by_code(self, code, qty=None):
        """
        Consume stock based on barcode or lot name.
        Example code: 'PKG0000005/3'
        """
        self.ensure_one()

        embedded_qty = None
        if "/" in code:
            tail = code.split("/", 1)[1]
            tail = tail.split("/", 1)[0]
            try:
                embedded_qty = float(tail)
            except Exception:
                embedded_qty = None

        target_qty = qty if qty is not None else embedded_qty
        if target_qty is None:
            target_qty = self.quantity

        if target_qty <= 0:
            raise UserError(_("Quantity to consume must be positive."))

        new_qty = self.quantity - target_qty
        if new_qty < 0:
            new_qty = 0.0

        self.with_context(inventory_mode=True).write({"inventory_quantity": new_qty})
        self.action_apply_inventory()
        return new_qty



# models/product_template.py
from odoo import api, fields, models, _
from odoo.exceptions import UserError

class ProductTemplate(models.Model):
    _inherit = "product.template"

    def action_print_lot_barcodes(self):
        self.ensure_one()
        Quant = self.env['stock.quant'].sudo()

        domain = [
            ('product_id.product_tmpl_id', '=', self.id),
            ('quantity', '>', 0),
            ('location_id.usage', '=', 'internal'),
            ('company_id', '=', self.env.company.id),
            ('lot_id', '!=', False),
        ]

        loc = self.env.context.get('search_default_location_id')
        if loc:
            domain.append(('location_id', '=', loc))

        quants = Quant.search(domain, order="location_id, lot_id, id")
        if not quants:
            raise UserError(_("No internal quants with lots to print for this product."))

        for q in quants:
            if not q.scan_barcode:
                seq = q._seq().sudo()
                code, num = q._get_next_free_barcode(seq)
                q.scan_barcode = code
                q._bump_sequence(seq, num + 1)


        action = self.env.ref('stock_quantity_scan.report_lot_barcodes_action')
        return action.report_action(self, data={"quant_ids": quants.ids})

    def action_generate_quant_barcodes(self):
        self.ensure_one()
        quants = self.env['stock.quant'].sudo().search([
            ('product_id.product_tmpl_id', '=', self.id),
            ('quantity', '>', 0),
        ])

        # ✅ FIX: use _get_next_free_barcode here too
        for q in quants:
            if not q.scan_barcode:
                seq = q._seq().sudo()
                code, num = q._get_next_free_barcode(seq)
                q.scan_barcode = code
                q._bump_sequence(seq, num + 1)


        return True

    def action_open_lot_barcode_wizard(self):
        self.ensure_one()
        return {
            "name": _("Print Lot Barcodes"),
            "type": "ir.actions.act_window",
            "res_model": "stock.lot.barcode.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_product_tmpl_id": self.id,
            },
        }
