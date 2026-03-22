from odoo import api, fields, models, _


class CoPurchaseRequestLine(models.Model):
    _name = 'co.purchase.request.line'
    _description = 'Purchase Request Line'
    _order = 'sequence, id'

    sequence = fields.Integer(string='Sequence', default=10)
    request_id = fields.Many2one(
        'co.purchase.request',
        string='Purchase Request',
        required=True,
        ondelete='cascade',
        index=True,
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
    estimated_price = fields.Float(
        string='Estimated Price',
    )
    subtotal = fields.Float(
        string='Subtotal',
        compute='_compute_subtotal',
        store=True,
    )
    supplier_id = fields.Many2one(
        'res.partner',
        string='Preferred Supplier',
        domain="[('supplier_rank', '>', 0)]",
    )
    reason = fields.Text(string='Reason / Justification')
    department_id = fields.Many2one(
        related='request_id.department_id',
        string='Department',
        store=True,
        readonly=True,
    )
    state = fields.Selection(
        related='request_id.state',
        string='Status',
        store=True,
        readonly=True,
    )
    company_id = fields.Many2one(
        related='request_id.company_id',
        store=True,
    )

    @api.depends('quantity', 'estimated_price')
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.quantity * line.estimated_price

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            # Set default supplier from product's seller_ids
            sellers = self.product_id.seller_ids
            if sellers:
                self.supplier_id = sellers[0].partner_id.id
            # Set estimated price from standard_price
            self.estimated_price = self.product_id.standard_price
