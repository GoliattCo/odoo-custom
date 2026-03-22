from odoo import api, fields, models, _
from odoo.exceptions import UserError


class CoRestaurantProduction(models.Model):
    _name = 'co.restaurant.production'
    _description = 'Recipe Production'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    name = fields.Char(
        string='Reference',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New'),
    )
    recipe_id = fields.Many2one(
        'co.restaurant.recipe',
        string='Recipe',
        required=True,
        tracking=True,
    )
    date = fields.Datetime(
        string='Production Date',
        default=fields.Datetime.now,
        required=True,
        tracking=True,
    )
    origin = fields.Selection([
        ('manual', 'Manual'),
        ('pos', 'POS Order'),
    ], string='Origin', default='manual', required=True, tracking=True)
    pos_order_ref = fields.Char(
        string='POS Order Reference',
        help='Reference to the POS order that triggered this production.',
    )
    quantity = fields.Float(
        string='Planned Quantity (Portions)',
        required=True,
        default=1.0,
        digits='Product Unit of Measure',
        tracking=True,
    )
    actual_quantity = fields.Float(
        string='Actual Quantity (Portions)',
        digits='Product Unit of Measure',
        help='Actual portions produced. Fill after production is done.',
    )
    variance_qty = fields.Float(
        string='Variance (Portions)',
        compute='_compute_variance',
        store=True,
        digits='Product Unit of Measure',
    )
    variance_pct = fields.Float(
        string='Variance %',
        compute='_compute_variance',
        store=True,
        digits=(5, 2),
    )
    line_ids = fields.One2many(
        'co.restaurant.production.line',
        'production_id',
        string='Ingredients Consumed',
        copy=True,
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('in_progress', 'In Progress'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', tracking=True)
    total_cost = fields.Float(
        string='Total Cost',
        compute='_compute_total_cost',
        store=True,
        digits='Product Price',
    )
    cost_per_portion = fields.Float(
        string='Actual Cost/Portion',
        compute='_compute_total_cost',
        store=True,
        digits='Product Price',
    )
    warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Warehouse',
        default=lambda self: self.env['stock.warehouse'].search(
            [('company_id', '=', self.env.company.id)], limit=1
        ),
    )
    location_id = fields.Many2one(
        'stock.location',
        string='Source Location',
        help='Location from which ingredients are consumed.',
    )
    notes = fields.Text(string='Notes')
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        related='company_id.currency_id',
        string='Currency',
    )

    @api.depends('quantity', 'actual_quantity')
    def _compute_variance(self):
        for rec in self:
            rec.variance_qty = rec.actual_quantity - rec.quantity
            rec.variance_pct = (
                ((rec.actual_quantity - rec.quantity) / rec.quantity * 100.0)
                if rec.quantity else 0.0
            )

    @api.depends('line_ids.subtotal', 'actual_quantity')
    def _compute_total_cost(self):
        for rec in self:
            rec.total_cost = sum(rec.line_ids.mapped('subtotal'))
            rec.cost_per_portion = (
                rec.total_cost / rec.actual_quantity
                if rec.actual_quantity else 0.0
            )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'co.restaurant.production'
                ) or _('New')
        return super().create(vals_list)

    def action_confirm(self):
        for rec in self:
            if not rec.line_ids:
                rec._populate_lines_from_recipe()
            rec.state = 'confirmed'

    def action_start(self):
        self.write({'state': 'in_progress'})

    def action_done(self):
        for rec in self:
            if not rec.actual_quantity:
                rec.actual_quantity = rec.quantity
            rec.state = 'done'
            rec._create_stock_moves()

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_reset_draft(self):
        self.write({'state': 'draft'})

    def _populate_lines_from_recipe(self):
        """Fill production lines from recipe ingredients scaled to quantity."""
        self.ensure_one()
        if not self.recipe_id or not self.recipe_id.line_ids:
            return
        scale = self.quantity / self.recipe_id.yield_qty if self.recipe_id.yield_qty else 1.0
        lines = []
        for rl in self.recipe_id.line_ids:
            lines.append((0, 0, {
                'product_id': rl.product_id.id,
                'planned_qty': rl.gross_quantity * scale,
                'actual_qty': rl.gross_quantity * scale,
                'uom_id': rl.uom_id.id,
                'unit_cost': rl.unit_cost,
            }))
        self.line_ids = lines

    def _create_stock_moves(self):
        """Create stock moves for ingredient consumption."""
        self.ensure_one()
        if not self.location_id:
            return
        dest_location = self.env.ref('stock.stock_location_production', raise_if_not_found=False)
        if not dest_location:
            return
        for line in self.line_ids:
            if line.actual_qty <= 0:
                continue
            move_vals = {
                'name': _('%(prod)s: %(ingredient)s', prod=self.name, ingredient=line.product_id.display_name),
                'product_id': line.product_id.id,
                'product_uom_qty': line.actual_qty,
                'product_uom': line.uom_id.id,
                'location_id': self.location_id.id,
                'location_dest_id': dest_location.id,
                'origin': self.name,
                'company_id': self.company_id.id,
            }
            move = self.env['stock.move'].create(move_vals)
            move._action_confirm()
            move._action_assign()
            move._action_done()

    @api.onchange('recipe_id', 'quantity')
    def _onchange_recipe_quantity(self):
        if self.recipe_id and self.quantity:
            self._populate_lines_from_recipe()


class CoRestaurantProductionLine(models.Model):
    _name = 'co.restaurant.production.line'
    _description = 'Production Ingredient Line'
    _order = 'sequence, id'

    production_id = fields.Many2one(
        'co.restaurant.production',
        string='Production',
        required=True,
        ondelete='cascade',
        index=True,
    )
    sequence = fields.Integer(string='Sequence', default=10)
    product_id = fields.Many2one(
        'product.product',
        string='Ingredient',
        required=True,
    )
    planned_qty = fields.Float(
        string='Planned Qty',
        digits='Product Unit of Measure',
    )
    actual_qty = fields.Float(
        string='Actual Qty',
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
    subtotal = fields.Float(
        string='Subtotal',
        compute='_compute_subtotal',
        store=True,
        digits='Product Price',
    )
    variance_qty = fields.Float(
        string='Variance',
        compute='_compute_variance',
        store=True,
        digits='Product Unit of Measure',
    )
    variance_pct = fields.Float(
        string='Variance %',
        compute='_compute_variance',
        store=True,
        digits=(5, 2),
    )

    @api.depends('actual_qty', 'unit_cost')
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.actual_qty * line.unit_cost

    @api.depends('planned_qty', 'actual_qty')
    def _compute_variance(self):
        for line in self:
            line.variance_qty = line.actual_qty - line.planned_qty
            line.variance_pct = (
                ((line.actual_qty - line.planned_qty) / line.planned_qty * 100.0)
                if line.planned_qty else 0.0
            )
