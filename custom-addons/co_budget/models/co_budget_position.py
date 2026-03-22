from odoo import api, fields, models


class CoBudgetPosition(models.Model):
    _name = 'co.budget.position'
    _description = 'Budget Position'
    _order = 'name'

    name = fields.Char(
        string='Position Name',
        required=True,
        translate=True,
    )
    code = fields.Char(
        string='Code',
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )
    account_ids = fields.Many2many(
        'account.account',
        'co_budget_position_account_rel',
        'position_id',
        'account_id',
        string='Accounts',
        help='Accounts grouped under this budget position.',
    )
    active = fields.Boolean(
        string='Active',
        default=True,
    )
    description = fields.Text(
        string='Description',
        translate=True,
    )
    line_ids = fields.One2many(
        'co.budget.line',
        'budget_position_id',
        string='Budget Lines',
    )

    _sql_constraints = [
        ('code_company_uniq', 'unique(code, company_id)',
         'The budget position code must be unique per company.'),
    ]
