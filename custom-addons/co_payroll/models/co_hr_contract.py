from odoo import api, fields, models


class HrContract(models.Model):
    _inherit = 'hr.contract'

    # -- Colombian contract fields --
    co_contract_type = fields.Selection([
        ('indefinido', 'Término Indefinido'),
        ('fijo', 'Término Fijo'),
        ('obra_labor', 'Obra o Labor'),
        ('aprendizaje', 'Contrato de Aprendizaje'),
    ], string='CO Contract Type', default='indefinido', tracking=True)

    co_integral_salary = fields.Boolean(
        string='Integral Salary',
        help='Salario integral (>= 13 SMLMV). Transport allowance and some '
             'provisions are handled differently.',
        tracking=True,
    )

    co_transport_allowance = fields.Float(
        string='Transport Allowance',
        compute='_compute_co_transport_allowance',
        store=True,
        help='Auxilio de transporte. Applies when salary <= 2 SMLMV.',
    )

    co_probation_end_date = fields.Date(string='Probation End Date')

    co_work_schedule = fields.Selection([
        ('full_time', 'Full Time (48h/week)'),
        ('part_time', 'Part Time'),
    ], string='Work Schedule', default='full_time')

    co_eps_id = fields.Many2one('co.eps.entity', string='EPS')
    co_afp_id = fields.Many2one('co.afp.entity', string='AFP (Pension Fund)')
    co_arl_id = fields.Many2one('co.arl.entity', string='ARL Entity')
    co_arl_risk_level_id = fields.Many2one(
        'co.arl.risk.level', string='ARL Risk Level',
    )
    co_caja_compensacion = fields.Char(string='Caja de Compensación')

    co_pay_frequency = fields.Selection([
        ('monthly', 'Monthly'),
        ('biweekly', 'Biweekly (Quincenal)'),
    ], string='Pay Frequency', default='monthly')

    co_hiring_request_id = fields.Many2one(
        'co.hiring.request', string='Hiring Request',
    )

    @api.depends('wage')
    def _compute_co_transport_allowance(self):
        constants = self.env['co.payroll.constants'].get_current()
        smlmv = constants.smlmv if constants else 1300000
        transport = constants.transport_allowance if constants else 162000
        for contract in self:
            if contract.co_integral_salary:
                contract.co_transport_allowance = 0.0
            elif contract.wage <= (2 * smlmv):
                contract.co_transport_allowance = transport
            else:
                contract.co_transport_allowance = 0.0
