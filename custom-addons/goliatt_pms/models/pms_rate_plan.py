from odoo import fields, models


class PmsRatePlan(models.Model):
    _name = 'pms.rate.plan'
    _description = 'Rate Plan'
    _order = 'name'

    name = fields.Char(required=True, string='Rate Plan')
    code = fields.Char(string='Code')
    property_id = fields.Many2one(
        'pms.property',
        string='Property',
    )
    rate_type = fields.Selection(
        [
            ('public', 'Public'),
            ('corporate', 'Corporate'),
            ('group', 'Group'),
            ('promotional', 'Promotional'),
            ('package', 'Package'),
        ],
        string='Rate Type',
        default='public',
    )
    meal_plan = fields.Selection(
        [
            ('room_only', 'Room Only'),
            ('bed_breakfast', 'Bed & Breakfast'),
            ('half_board', 'Half Board'),
            ('full_board', 'Full Board'),
            ('all_inclusive', 'All Inclusive'),
        ],
        string='Meal Plan',
        default='room_only',
    )
    is_derived = fields.Boolean(string='Is Derived Rate')
    parent_rate_plan_id = fields.Many2one(
        'pms.rate.plan',
        string='Parent Rate Plan',
    )
    derivation_type = fields.Selection(
        [
            ('percentage', 'Percentage'),
            ('fixed', 'Fixed Amount'),
        ],
        string='Derivation Type',
    )
    derivation_value = fields.Float(string='Derivation Value')
    date_start = fields.Date(string='Valid From')
    date_end = fields.Date(string='Valid Until')
    min_stay = fields.Integer(string='Minimum Stay (nights)')
    active = fields.Boolean(default=True)
