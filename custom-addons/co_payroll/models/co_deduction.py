from odoo import api, fields, models


class CoDeduction(models.Model):
    _name = 'co.deduction'
    _description = 'Manual Deduction'
    _order = 'date desc'

    name = fields.Char(string='Description', required=True)
    employee_id = fields.Many2one(
        'hr.employee', string='Employee', required=True,
    )
    deduction_type = fields.Selection([
        ('manual', 'Manual Deduction'),
        ('restaurant', 'Restaurant / Cafeteria'),
        ('company_purchase', 'Company Product Purchase'),
        ('other', 'Other'),
    ], string='Type', required=True, default='manual')
    amount = fields.Float(string='Amount', required=True)
    date = fields.Date(string='Date', required=True, default=fields.Date.today)
    payslip_id = fields.Many2one('co.payslip', string='Applied on Payslip')
    applied = fields.Boolean(string='Applied', default=False)
    notes = fields.Text(string='Notes')
