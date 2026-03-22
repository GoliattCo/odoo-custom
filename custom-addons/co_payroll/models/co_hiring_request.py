from odoo import api, fields, models


class CoHiringRequest(models.Model):
    _name = 'co.hiring.request'
    _description = 'Hiring Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    name = fields.Char(
        string='Reference', required=True, copy=False, readonly=True,
        default='New',
    )
    position = fields.Char(string='Position', required=True, tracking=True)
    department_id = fields.Many2one(
        'hr.department', string='Department', required=True, tracking=True,
    )
    job_id = fields.Many2one('hr.job', string='Job Position')
    number_of_positions = fields.Integer(string='Number of Positions', default=1)
    requirements = fields.Html(string='Requirements')
    justification = fields.Text(string='Justification')
    requested_by = fields.Many2one(
        'res.users', string='Requested By', default=lambda self: self.env.user,
        tracking=True,
    )
    approved_by = fields.Many2one('res.users', string='Approved By', tracking=True)
    request_date = fields.Date(
        string='Request Date', default=fields.Date.today, required=True,
    )
    expected_start_date = fields.Date(string='Expected Start Date')
    salary_range_min = fields.Float(string='Salary Range Min')
    salary_range_max = fields.Float(string='Salary Range Max')
    contract_type = fields.Selection([
        ('indefinido', 'Indefinido'),
        ('fijo', 'Término Fijo'),
        ('obra_labor', 'Obra o Labor'),
        ('aprendizaje', 'Aprendizaje'),
    ], string='Contract Type', default='indefinido')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('approved', 'Approved'),
        ('recruiting', 'Recruiting'),
        ('filled', 'Filled'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', tracking=True, required=True)
    notes = fields.Text(string='Notes')
    employee_id = fields.Many2one(
        'hr.employee', string='Hired Employee',
        help='Employee hired for this position',
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'co.hiring.request'
                ) or 'New'
        return super().create(vals_list)

    def action_submit(self):
        self.write({'state': 'submitted'})

    def action_approve(self):
        self.write({
            'state': 'approved',
            'approved_by': self.env.user.id,
        })

    def action_start_recruiting(self):
        self.write({'state': 'recruiting'})

    def action_mark_filled(self):
        self.write({'state': 'filled'})

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_reset_draft(self):
        self.write({'state': 'draft'})
