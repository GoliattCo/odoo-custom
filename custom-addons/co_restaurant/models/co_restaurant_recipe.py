from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class CoRestaurantRecipeCategory(models.Model):
    _name = 'co.restaurant.recipe.category'
    _description = 'Recipe Category'
    _order = 'sequence, name'

    name = fields.Char(string='Name', required=True, translate=True)
    sequence = fields.Integer(string='Sequence', default=10)
    active = fields.Boolean(string='Active', default=True)
    recipe_count = fields.Integer(
        string='Recipe Count',
        compute='_compute_recipe_count',
    )

    def _compute_recipe_count(self):
        data = self.env['co.restaurant.recipe'].read_group(
            [('category_id', 'in', self.ids)],
            ['category_id'],
            ['category_id'],
        )
        mapped = {d['category_id'][0]: d['category_id_count'] for d in data}
        for rec in self:
            rec.recipe_count = mapped.get(rec.id, 0)


class CoRestaurantRecipe(models.Model):
    _name = 'co.restaurant.recipe'
    _description = 'Restaurant Recipe'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name'

    name = fields.Char(
        string='Recipe Name',
        required=True,
        tracking=True,
        translate=True,
    )
    active = fields.Boolean(string='Active', default=True)
    image = fields.Binary(string='Photo', attachment=True)
    category_id = fields.Many2one(
        'co.restaurant.recipe.category',
        string='Category',
        tracking=True,
    )
    product_id = fields.Many2one(
        'product.product',
        string='Produced Product',
        help='The finished dish product that this recipe produces.',
        tracking=True,
    )
    line_ids = fields.One2many(
        'co.restaurant.recipe.line',
        'recipe_id',
        string='Ingredients',
        copy=True,
    )
    instructions = fields.Html(
        string='Preparation Instructions',
    )
    yield_qty = fields.Float(
        string='Yield (Portions)',
        default=1.0,
        tracking=True,
        help='Number of portions this recipe produces.',
    )
    yield_uom_id = fields.Many2one(
        'uom.uom',
        string='Yield UoM',
        help='Unit of measure for the yield (e.g., portions, liters).',
    )
    total_cost = fields.Float(
        string='Total Cost',
        compute='_compute_costs',
        store=True,
        digits='Product Price',
    )
    cost_per_portion = fields.Float(
        string='Cost per Portion',
        compute='_compute_costs',
        store=True,
        digits='Product Price',
    )
    selling_price = fields.Float(
        string='Selling Price',
        digits='Product Price',
        tracking=True,
    )
    food_cost_pct = fields.Float(
        string='Food Cost %',
        compute='_compute_costs',
        store=True,
        digits=(5, 2),
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('archived', 'Archived'),
    ], string='Status', default='draft', tracking=True)
    notes = fields.Text(string='Notes')
    production_ids = fields.One2many(
        'co.restaurant.production',
        'recipe_id',
        string='Productions',
    )
    production_count = fields.Integer(
        string='Production Count',
        compute='_compute_production_count',
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        related='company_id.currency_id',
        string='Currency',
    )

    @api.depends('line_ids.subtotal', 'yield_qty', 'selling_price')
    def _compute_costs(self):
        for recipe in self:
            total = sum(recipe.line_ids.mapped('subtotal'))
            recipe.total_cost = total
            recipe.cost_per_portion = total / recipe.yield_qty if recipe.yield_qty else 0.0
            recipe.food_cost_pct = (
                (recipe.cost_per_portion / recipe.selling_price * 100.0)
                if recipe.selling_price else 0.0
            )

    def _compute_production_count(self):
        data = self.env['co.restaurant.production'].read_group(
            [('recipe_id', 'in', self.ids)],
            ['recipe_id'],
            ['recipe_id'],
        )
        mapped = {d['recipe_id'][0]: d['recipe_id_count'] for d in data}
        for rec in self:
            rec.production_count = mapped.get(rec.id, 0)

    def action_activate(self):
        self.write({'state': 'active'})

    def action_archive_recipe(self):
        self.write({'state': 'archived'})

    def action_reset_draft(self):
        self.write({'state': 'draft'})

    def action_view_productions(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Productions'),
            'res_model': 'co.restaurant.production',
            'view_mode': 'list,form',
            'domain': [('recipe_id', '=', self.id)],
            'context': {'default_recipe_id': self.id},
        }

    def action_create_production(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('New Production'),
            'res_model': 'co.restaurant.production',
            'view_mode': 'form',
            'context': {'default_recipe_id': self.id},
        }

    @api.constrains('yield_qty')
    def _check_yield_qty(self):
        for rec in self:
            if rec.yield_qty <= 0:
                raise ValidationError(_('Yield must be greater than zero.'))


class CoRestaurantRecipeLine(models.Model):
    _name = 'co.restaurant.recipe.line'
    _description = 'Recipe Ingredient Line'
    _order = 'sequence, id'

    recipe_id = fields.Many2one(
        'co.restaurant.recipe',
        string='Recipe',
        required=True,
        ondelete='cascade',
        index=True,
    )
    sequence = fields.Integer(string='Sequence', default=10)
    product_id = fields.Many2one(
        'product.product',
        string='Ingredient',
        required=True,
        domain=[('type', '=', 'consu')],
    )
    quantity = fields.Float(
        string='Quantity',
        required=True,
        default=1.0,
        digits='Product Unit of Measure',
    )
    uom_id = fields.Many2one(
        'uom.uom',
        string='Unit of Measure',
        required=True,
    )
    unit_cost = fields.Float(
        string='Unit Cost',
        compute='_compute_unit_cost',
        store=True,
        digits='Product Price',
    )
    subtotal = fields.Float(
        string='Subtotal',
        compute='_compute_subtotal',
        store=True,
        digits='Product Price',
    )
    loss_pct = fields.Float(
        string='Loss %',
        default=0.0,
        digits=(5, 2),
        help='Expected preparation loss percentage for this ingredient.',
    )
    gross_quantity = fields.Float(
        string='Gross Quantity',
        compute='_compute_gross_quantity',
        store=True,
        digits='Product Unit of Measure',
        help='Quantity needed including preparation loss.',
    )
    notes = fields.Char(string='Notes')

    @api.depends('product_id', 'product_id.standard_price')
    def _compute_unit_cost(self):
        for line in self:
            line.unit_cost = line.product_id.standard_price if line.product_id else 0.0

    @api.depends('gross_quantity', 'unit_cost')
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.gross_quantity * line.unit_cost

    @api.depends('quantity', 'loss_pct')
    def _compute_gross_quantity(self):
        for line in self:
            if line.loss_pct >= 100:
                line.gross_quantity = line.quantity
            else:
                line.gross_quantity = line.quantity / (1 - line.loss_pct / 100.0) if line.loss_pct else line.quantity

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.uom_id = self.product_id.uom_id
