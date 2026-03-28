from odoo import api, fields, models, _


class HrContract(models.Model):
    _name = 'hr.contract'
    _description = 'Employee Contract'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_start desc, id desc'

    name = fields.Char(
        string='Contract Reference',
        required=True,
        tracking=True,
    )
    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        required=True,
        tracking=True,
        ondelete='cascade',
    )
    department_id = fields.Many2one(
        'hr.department',
        string='Department',
        related='employee_id.department_id',
        store=True,
    )
    job_id = fields.Many2one(
        'hr.job',
        string='Job Position',
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='company_id.currency_id',
    )
    wage = fields.Monetary(
        string='Wage',
        required=True,
        tracking=True,
        help='Basic monthly salary.',
    )
    state = fields.Selection(
        [
            ('draft', 'New'),
            ('open', 'Running'),
            ('close', 'Expired'),
            ('cancel', 'Cancelled'),
        ],
        string='Status',
        default='draft',
        tracking=True,
    )
    date_start = fields.Date(
        string='Start Date',
        required=True,
        default=fields.Date.context_today,
    )
    date_end = fields.Date(
        string='End Date',
    )
    notes = fields.Html(
        string='Notes',
    )
    def action_open(self):
        for contract in self:
            contract.state = 'open'

    def action_close(self):
        for contract in self:
            contract.state = 'close'

    def action_cancel(self):
        for contract in self:
            contract.state = 'cancel'

    def action_draft(self):
        for contract in self:
            contract.state = 'draft'
