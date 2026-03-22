from odoo import api, fields, models, _
from odoo.exceptions import UserError


class CoRestaurantInventoryAdjustment(models.TransientModel):
    _name = 'co.restaurant.inventory.adjustment'
    _description = 'Inventory Adjustment Wizard'

    date = fields.Datetime(
        string='Count Date',
        default=fields.Datetime.now,
        required=True,
    )
    location_id = fields.Many2one(
        'stock.location',
        string='Location',
        required=True,
        domain=[('usage', '=', 'internal')],
    )
    line_ids = fields.One2many(
        'co.restaurant.inventory.adjustment.line',
        'wizard_id',
        string='Count Lines',
    )
    notes = fields.Text(string='Notes')
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
    )

    def action_load_products(self):
        """Load all products with stock in the selected location."""
        self.ensure_one()
        self.line_ids.unlink()
        quants = self.env['stock.quant'].search([
            ('location_id', '=', self.location_id.id),
            ('quantity', '!=', 0),
        ])
        lines = []
        for quant in quants:
            lines.append((0, 0, {
                'product_id': quant.product_id.id,
                'uom_id': quant.product_id.uom_id.id,
                'theoretical_qty': quant.quantity,
                'counted_qty': 0.0,
                'unit_cost': quant.product_id.standard_price,
            }))
        self.line_ids = lines
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_apply_adjustment(self):
        """Create stock quant adjustments for variances."""
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_('No products to adjust. Load products first.'))

        adjustments_made = []
        for line in self.line_ids:
            if line.variance_qty == 0:
                continue
            # Use stock.quant's built-in inventory adjustment
            quant = self.env['stock.quant'].search([
                ('product_id', '=', line.product_id.id),
                ('location_id', '=', self.location_id.id),
            ], limit=1)
            if quant:
                quant.with_context(inventory_mode=True).write({
                    'inventory_quantity': line.counted_qty,
                })
                quant.action_apply_inventory()
            else:
                # Create new quant if product not present
                quant = self.env['stock.quant'].with_context(inventory_mode=True).create({
                    'product_id': line.product_id.id,
                    'location_id': self.location_id.id,
                    'inventory_quantity': line.counted_qty,
                })
                quant.action_apply_inventory()
            adjustments_made.append(line.product_id.display_name)

        if adjustments_made:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Inventory Adjusted'),
                    'message': _('%d products adjusted.') % len(adjustments_made),
                    'type': 'success',
                    'sticky': False,
                },
            }
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('No Adjustments'),
                'message': _('No variances found. All counts match.'),
                'type': 'warning',
                'sticky': False,
            },
        }


class CoRestaurantInventoryAdjustmentLine(models.TransientModel):
    _name = 'co.restaurant.inventory.adjustment.line'
    _description = 'Inventory Adjustment Line'
    _order = 'product_id'

    wizard_id = fields.Many2one(
        'co.restaurant.inventory.adjustment',
        string='Wizard',
        required=True,
        ondelete='cascade',
    )
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        required=True,
    )
    uom_id = fields.Many2one(
        'uom.uom',
        string='UoM',
    )
    theoretical_qty = fields.Float(
        string='Expected Qty',
        digits='Product Unit of Measure',
    )
    counted_qty = fields.Float(
        string='Counted Qty',
        digits='Product Unit of Measure',
    )
    variance_qty = fields.Float(
        string='Variance',
        compute='_compute_variance',
        digits='Product Unit of Measure',
    )
    variance_pct = fields.Float(
        string='Variance %',
        compute='_compute_variance',
        digits=(5, 2),
    )
    unit_cost = fields.Float(
        string='Unit Cost',
        digits='Product Price',
    )
    variance_cost = fields.Float(
        string='Variance Cost',
        compute='_compute_variance',
        digits='Product Price',
    )

    @api.depends('theoretical_qty', 'counted_qty', 'unit_cost')
    def _compute_variance(self):
        for line in self:
            line.variance_qty = line.counted_qty - line.theoretical_qty
            line.variance_pct = (
                (line.variance_qty / line.theoretical_qty * 100.0)
                if line.theoretical_qty else 0.0
            )
            line.variance_cost = line.variance_qty * line.unit_cost
