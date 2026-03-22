from odoo import api, fields, models, _


class CoInventoryFormula(models.Model):
    _name = 'co.inventory.formula'
    _description = 'Inventory Valuation Formula'
    _order = 'sequence, id'

    name = fields.Char(
        string='Concept Name',
        required=True,
        translate=True,
    )
    sequence = fields.Integer(string='Sequence', default=10)
    active = fields.Boolean(string='Active', default=True)
    method = fields.Selection(
        [
            ('standard', 'Standard Cost'),
            ('average', 'Weighted Average'),
            ('fifo', 'FIFO (First In First Out)'),
        ],
        string='Valuation Method',
        required=True,
        default='average',
    )
    formula_description = fields.Text(
        string='Formula Description',
        help='Human-readable description of the formula used for this valuation concept.',
        translate=True,
    )
    formula_expression = fields.Text(
        string='Formula Expression',
        help=(
            'Technical expression for the formula. For display/documentation purposes. '
            'Example: "Unit Cost = Total Cost / Total Quantity"'
        ),
    )
    product_category_ids = fields.Many2many(
        'product.category',
        'co_inventory_formula_categ_rel',
        'formula_id',
        'categ_id',
        string='Applicable Product Categories',
        help='If empty, applies to all categories.',
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
    )
    notes = fields.Html(string='Notes')

    def name_get(self):
        return [
            (rec.id, '%s (%s)' % (rec.name, dict(self._fields['method'].selection).get(rec.method, '')))
            for rec in self
        ]
