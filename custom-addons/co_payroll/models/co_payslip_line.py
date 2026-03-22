from odoo import fields, models


class CoPayslipLine(models.Model):
    _name = 'co.payslip.line'
    _description = 'Payslip Line'
    _order = 'sequence, id'

    payslip_id = fields.Many2one(
        'co.payslip', string='Payslip', required=True, ondelete='cascade',
    )
    code = fields.Char(string='Code', required=True)
    name = fields.Char(string='Description', required=True)
    line_type = fields.Selection([
        ('earning', 'Earning (Devengado)'),
        ('deduction', 'Deduction (Deducción)'),
        ('employer', 'Employer Contribution'),
        ('provision', 'Provision'),
    ], string='Type', required=True)
    amount = fields.Float(string='Amount')
    sequence = fields.Integer(string='Sequence', default=10)
    employee_id = fields.Many2one(
        related='payslip_id.employee_id', store=True,
    )
    date_from = fields.Date(related='payslip_id.date_from', store=True)
    date_to = fields.Date(related='payslip_id.date_to', store=True)
