from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class CoRestaurantPresentationEquiv(models.Model):
    _name = 'co.restaurant.presentation.equiv'
    _description = 'Product Presentation Equivalence'
    _order = 'product_id, name'
    _rec_name = 'display_name'

    name = fields.Char(
        string='Equivalence Name',
        required=True,
        help='Descriptive name, e.g. "Chicken breast to grams".',
    )
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        required=True,
        index=True,
    )
    purchase_qty = fields.Float(
        string='Purchase Quantity',
        required=True,
        default=1.0,
        digits='Product Unit of Measure',
        help='Quantity in the purchase unit (e.g., 1 breast).',
    )
    purchase_uom_id = fields.Many2one(
        'uom.uom',
        string='Purchase UoM',
        required=True,
        help='Unit used when purchasing (e.g., Units).',
    )
    recipe_qty = fields.Float(
        string='Recipe Quantity',
        required=True,
        digits='Product Unit of Measure',
        help='Equivalent quantity in the recipe unit (e.g., 200 g).',
    )
    recipe_uom_id = fields.Many2one(
        'uom.uom',
        string='Recipe UoM',
        required=True,
        help='Unit used in recipes (e.g., g).',
    )
    factor = fields.Float(
        string='Conversion Factor',
        compute='_compute_factor',
        store=True,
        digits=(12, 6),
        help='recipe_qty / purchase_qty',
    )
    active = fields.Boolean(string='Active', default=True)
    notes = fields.Text(string='Notes')
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
    )

    @api.depends('purchase_qty', 'recipe_qty')
    def _compute_factor(self):
        for rec in self:
            rec.factor = rec.recipe_qty / rec.purchase_qty if rec.purchase_qty else 0.0

    @api.constrains('purchase_qty', 'recipe_qty')
    def _check_quantities(self):
        for rec in self:
            if rec.purchase_qty <= 0 or rec.recipe_qty <= 0:
                raise ValidationError(
                    _('Both purchase and recipe quantities must be greater than zero.')
                )

    def name_get(self):
        result = []
        for rec in self:
            name = '%s: %s %s = %s %s' % (
                rec.product_id.display_name,
                rec.purchase_qty,
                rec.purchase_uom_id.name,
                rec.recipe_qty,
                rec.recipe_uom_id.name,
            )
            result.append((rec.id, name))
        return result
