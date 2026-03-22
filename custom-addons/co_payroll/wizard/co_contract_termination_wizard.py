from odoo import models, fields, api
from datetime import date


class CoContractTerminationWizard(models.TransientModel):
    _name = 'co.contract.termination.wizard'
    _description = 'Contract Termination Wizard'

    employee_id = fields.Many2one('hr.employee', string='Employee', required=True)
    contract_id = fields.Many2one('hr.contract', string='Contract', required=True,
                                  domain="[('employee_id', '=', employee_id), ('state', '=', 'open')]")
    termination_date = fields.Date(string='Termination Date', required=True, default=fields.Date.today)
    termination_reason = fields.Selection([
        ('mutual', 'Mutual Agreement'),
        ('just_cause', 'Just Cause'),
        ('no_cause', 'Without Just Cause'),
        ('resignation', 'Resignation'),
        ('end_term', 'End of Term'),
        ('retirement', 'Retirement'),
    ], string='Reason', required=True)

    pending_salary = fields.Float(string='Pending Salary', compute='_compute_liquidation')
    prima_amount = fields.Float(string='Prima de Servicios', compute='_compute_liquidation')
    cesantias_amount = fields.Float(string='Cesantias', compute='_compute_liquidation')
    intereses_cesantias = fields.Float(string='Intereses sobre Cesantias', compute='_compute_liquidation')
    vacaciones_amount = fields.Float(string='Vacaciones', compute='_compute_liquidation')
    indemnizacion_amount = fields.Float(string='Indemnizacion', compute='_compute_liquidation')
    total_liquidation = fields.Float(string='Total Liquidacion', compute='_compute_liquidation')

    @api.depends('contract_id', 'termination_date', 'termination_reason')
    def _compute_liquidation(self):
        for wiz in self:
            if not wiz.contract_id or not wiz.termination_date:
                wiz.pending_salary = wiz.prima_amount = wiz.cesantias_amount = 0
                wiz.intereses_cesantias = wiz.vacaciones_amount = wiz.indemnizacion_amount = 0
                wiz.total_liquidation = 0
                continue

            salary = wiz.contract_id.wage or 0
            start = wiz.contract_id.date_start
            end = wiz.termination_date
            days_year = (end - date(end.year, 1, 1)).days + 1 if start and end else 0
            days_total = (end - start).days + 1 if start and end else 0

            wiz.pending_salary = (salary / 30) * end.day
            wiz.prima_amount = (salary * days_year) / 360
            wiz.cesantias_amount = (salary * days_year) / 360
            wiz.intereses_cesantias = (wiz.cesantias_amount * days_year * 0.12) / 360
            wiz.vacaciones_amount = (salary * days_year) / 720

            if wiz.termination_reason == 'no_cause':
                wiz.indemnizacion_amount = salary * max(1, days_total / 365)
            else:
                wiz.indemnizacion_amount = 0

            wiz.total_liquidation = sum([
                wiz.pending_salary, wiz.prima_amount, wiz.cesantias_amount,
                wiz.intereses_cesantias, wiz.vacaciones_amount, wiz.indemnizacion_amount
            ])

    def action_confirm_termination(self):
        self.ensure_one()
        if self.contract_id:
            self.contract_id.write({'date_end': self.termination_date, 'state': 'close'})
        return {'type': 'ir.actions.act_window_close'}
