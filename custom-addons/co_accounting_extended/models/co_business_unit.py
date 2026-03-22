from odoo import api, fields, models


class CoBusinessUnit(models.Model):
    _name = 'co.business.unit'
    _description = 'Business Unit'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'sequence, name'

    name = fields.Char(
        string='Name',
        required=True,
        tracking=True,
        translate=True,
    )
    code = fields.Char(
        string='Code',
        required=True,
        tracking=True,
    )
    sequence = fields.Integer(string='Sequence', default=10)
    active = fields.Boolean(string='Active', default=True, tracking=True)
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )
    analytic_account_id = fields.Many2one(
        'account.analytic.account',
        string='Analytic Account',
        tracking=True,
        help='Link this business unit to an analytic account for reporting.',
    )
    responsible_id = fields.Many2one(
        'res.users',
        string='Responsible',
        tracking=True,
    )
    description = fields.Text(string='Description')
    move_line_ids = fields.One2many(
        'account.move.line',
        'business_unit_id',
        string='Journal Items',
    )
    move_line_count = fields.Integer(
        string='Journal Items Count',
        compute='_compute_move_line_count',
    )

    _sql_constraints = [
        ('code_company_uniq', 'unique(code, company_id)',
         'The code must be unique per company.'),
    ]

    @api.depends('move_line_ids')
    def _compute_move_line_count(self):
        for rec in self:
            rec.move_line_count = len(rec.move_line_ids)

    def name_get(self):
        return [(rec.id, f'[{rec.code}] {rec.name}') for rec in self]
