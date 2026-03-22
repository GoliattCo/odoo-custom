from odoo import api, fields, models, _
from odoo.exceptions import UserError


class CoWarehouseTransferWizard(models.TransientModel):
    _name = 'co.warehouse.transfer.wizard'
    _description = 'Inter-Warehouse Transfer Wizard'

    source_warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Source Warehouse',
        required=True,
    )
    dest_warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Destination Warehouse',
        required=True,
    )
    scheduled_date = fields.Datetime(
        string='Scheduled Date',
        default=fields.Datetime.now,
        required=True,
    )
    line_ids = fields.One2many(
        'co.warehouse.transfer.wizard.line',
        'wizard_id',
        string='Products',
    )
    notes = fields.Text(string='Notes')
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True,
    )

    @api.constrains('source_warehouse_id', 'dest_warehouse_id')
    def _check_warehouses(self):
        for wiz in self:
            if wiz.source_warehouse_id == wiz.dest_warehouse_id:
                raise UserError(_('Source and destination warehouses must be different.'))

    def action_create_transfer(self):
        """Create an internal transfer picking between the two warehouses."""
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_('Please add at least one product line.'))

        # Determine picking type: internal transfer of source warehouse
        picking_type = self.env['stock.picking.type'].search([
            ('warehouse_id', '=', self.source_warehouse_id.id),
            ('code', '=', 'internal'),
        ], limit=1)
        if not picking_type:
            raise UserError(_(
                'No internal transfer operation type found for warehouse "%s".'
            ) % self.source_warehouse_id.name)

        source_location = self.source_warehouse_id.lot_stock_id
        dest_location = self.dest_warehouse_id.lot_stock_id

        picking_vals = {
            'picking_type_id': picking_type.id,
            'location_id': source_location.id,
            'location_dest_id': dest_location.id,
            'scheduled_date': self.scheduled_date,
            'origin': _('Inter-Warehouse Transfer'),
            'note': self.notes,
            'company_id': self.company_id.id,
        }
        picking = self.env['stock.picking'].create(picking_vals)

        for line in self.line_ids:
            self.env['stock.move'].create({
                'name': line.product_id.display_name,
                'picking_id': picking.id,
                'product_id': line.product_id.id,
                'product_uom_qty': line.quantity,
                'product_uom': line.product_uom_id.id,
                'location_id': source_location.id,
                'location_dest_id': dest_location.id,
                'company_id': self.company_id.id,
            })

        picking.action_confirm()

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'stock.picking',
            'res_id': picking.id,
            'view_mode': 'form',
            'target': 'current',
        }


class CoWarehouseTransferWizardLine(models.TransientModel):
    _name = 'co.warehouse.transfer.wizard.line'
    _description = 'Inter-Warehouse Transfer Wizard Line'

    wizard_id = fields.Many2one(
        'co.warehouse.transfer.wizard',
        string='Wizard',
        required=True,
        ondelete='cascade',
    )
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        required=True,
    )
    product_uom_id = fields.Many2one(
        'uom.uom',
        string='Unit of Measure',
        related='product_id.uom_id',
        store=True,
        readonly=True,
    )
    quantity = fields.Float(
        string='Quantity',
        required=True,
        default=1.0,
    )
