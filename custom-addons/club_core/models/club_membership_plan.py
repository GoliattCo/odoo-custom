from odoo import fields, models


class ClubMembershipPlan(models.Model):
    _name = 'club.membership.plan'
    _description = 'Club Membership Plan'

    name = fields.Char(required=True, string='Plan Name', translate=True)
    fee = fields.Float(required=True, string='Fee Amount', digits=(10, 2))
    billing_period = fields.Selection(
        [('monthly', 'Monthly'), ('annual', 'Annual')],
        required=True,
        default='annual',
        string='Billing Period',
    )
    grace_period_days = fields.Integer(
        default=15, string='Grace Period (days)'
    )
    late_fee_amount = fields.Float(
        string='Late Fee Amount', digits=(10, 2)
    )
    golf_access = fields.Boolean(string='Golf Access')
    equestrian_access = fields.Boolean(string='Equestrian Access')
    tennis_access = fields.Boolean(string='Tennis Access')
    product_id = fields.Many2one(
        'product.product',
        string='Membership Product',
        required=True,
        domain=[('type', '=', 'service')],
    )
    late_fee_product_id = fields.Many2one(
        'product.product',
        string='Late Fee Product',
        domain=[('type', '=', 'service')],
    )
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('name_uniq', 'unique(name)', 'Membership plan name must be unique.'),
    ]
