from odoo import api, fields, models, _


class CoRestaurantWaste(models.Model):
    _name = 'co.restaurant.waste'
    _description = 'Production Waste Record'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    name = fields.Char(
        string='Reference',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New'),
    )
    date = fields.Datetime(
        string='Date',
        default=fields.Datetime.now,
        required=True,
        tracking=True,
    )
    production_id = fields.Many2one(
        'co.restaurant.production',
        string='Production',
        help='Related production order, if applicable.',
    )
    recipe_id = fields.Many2one(
        'co.restaurant.recipe',
        string='Recipe',
    )
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        required=True,
        tracking=True,
    )
    waste_type = fields.Selection([
        ('spoilage', 'Spoilage'),
        ('preparation', 'Preparation Waste'),
        ('overproduction', 'Overproduction'),
        ('expired', 'Expired'),
        ('other', 'Other'),
    ], string='Waste Type', required=True, tracking=True)
    quantity = fields.Float(
        string='Quantity',
        required=True,
        digits='Product Unit of Measure',
    )
    uom_id = fields.Many2one(
        'uom.uom',
        string='Unit of Measure',
        required=True,
    )
    unit_cost = fields.Float(
        string='Unit Cost',
        digits='Product Price',
    )
    total_cost = fields.Float(
        string='Total Cost',
        compute='_compute_total_cost',
        store=True,
        digits='Product Price',
    )
    responsible_id = fields.Many2one(
        'res.users',
        string='Responsible',
        default=lambda self: self.env.user,
    )
    location_id = fields.Many2one(
        'stock.location',
        string='Location',
    )
    notes = fields.Text(string='Notes')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
    ], string='Status', default='draft', tracking=True)
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        related='company_id.currency_id',
        string='Currency',
    )

    @api.depends('quantity', 'unit_cost')
    def _compute_total_cost(self):
        for rec in self:
            rec.total_cost = rec.quantity * rec.unit_cost

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'co.restaurant.waste'
                ) or _('New')
        return super().create(vals_list)

    def action_confirm(self):
        for rec in self:
            rec.state = 'confirmed'
            rec._create_stock_move()

    def _create_stock_move(self):
        """Create a stock move to record the waste exit from inventory."""
        self.ensure_one()
        if not self.location_id:
            return
        scrap_location = self.env['stock.location'].search(
            [('scrap_location', '=', True), ('company_id', '=', self.company_id.id)],
            limit=1,
        )
        if not scrap_location:
            scrap_location = self.env['stock.location'].search(
                [('scrap_location', '=', True)],
                limit=1,
            )
        if not scrap_location:
            return
        move_vals = {
            'name': _('Waste: %(ref)s', ref=self.name),
            'product_id': self.product_id.id,
            'product_uom_qty': self.quantity,
            'product_uom': self.uom_id.id,
            'location_id': self.location_id.id,
            'location_dest_id': scrap_location.id,
            'origin': self.name,
            'company_id': self.company_id.id,
        }
        move = self.env['stock.move'].create(move_vals)
        move._action_confirm()
        move._action_assign()
        move._action_done()

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.uom_id = self.product_id.uom_id
            self.unit_cost = self.product_id.standard_price
