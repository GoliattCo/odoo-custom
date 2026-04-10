from odoo import api, fields, models


class CoProductRequestLine(models.Model):
    _name = 'co.product.request.line'
    _description = 'Product Request Line'
    _order = 'sequence, id'

    sequence = fields.Integer(default=10)
    request_id = fields.Many2one(
        'co.product.request', required=True, ondelete='cascade', index=True)
    product_id = fields.Many2one('product.product', required=True)
    uom_id = fields.Many2one(
        'uom.uom', related='product_id.uom_id', store=True, readonly=True)
    qty_requested = fields.Float(string='Quantity Requested', required=True, default=1.0)
    qty_available = fields.Float(
        string='Available Stock', readonly=True,
        help='Quantity available in warehouse at time of stock check.')
    qty_to_transfer = fields.Float(string='Qty to Transfer')
    qty_to_purchase = fields.Float(string='Qty to Purchase')
    line_state = fields.Selection([
        ('pending', 'Pending'),
        ('available', 'Available'),
        ('partial', 'Partially Available'),
        ('unavailable', 'Unavailable'),
    ], string='Availability', default='pending', readonly=True)
    company_id = fields.Many2one(
        related='request_id.company_id', store=True)
