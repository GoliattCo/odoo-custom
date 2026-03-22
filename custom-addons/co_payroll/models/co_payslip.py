import math
from datetime import date

from odoo import api, fields, models
from odoo.exceptions import UserError


class CoPayslip(models.Model):
    _name = 'co.payslip'
    _description = 'Colombian Payslip (Nómina)'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_from desc, employee_id'

    name = fields.Char(
        string='Reference', required=True, copy=False, readonly=True,
        default='New',
    )
    employee_id = fields.Many2one(
        'hr.employee', string='Employee', required=True,
        states={'done': [('readonly', True)]}, tracking=True,
    )
    contract_id = fields.Many2one(
        'hr.contract', string='Contract',
        compute='_compute_contract', store=True, readonly=False,
    )
    department_id = fields.Many2one(
        related='employee_id.department_id', string='Department', store=True,
    )

    # Period
    date_from = fields.Date(
        string='Period Start', required=True,
        states={'done': [('readonly', True)]},
    )
    date_to = fields.Date(
        string='Period End', required=True,
        states={'done': [('readonly', True)]},
    )
    pay_frequency = fields.Selection([
        ('monthly', 'Monthly'),
        ('biweekly', 'Biweekly (Quincenal)'),
    ], string='Pay Frequency', default='monthly')

    # Worked days
    worked_days = fields.Float(
        string='Worked Days', default=30,
        states={'done': [('readonly', True)]},
    )
    total_days = fields.Float(string='Total Days in Period', default=30)

    # Earnings
    basic_salary = fields.Float(
        string='Basic Salary', compute='_compute_basic_salary', store=True,
    )
    transport_allowance = fields.Float(
        string='Transport Allowance',
        compute='_compute_basic_salary', store=True,
    )
    overtime_amount = fields.Float(
        string='Overtime', compute='_compute_overtime', store=True,
    )
    commissions = fields.Float(
        string='Commissions', states={'done': [('readonly', True)]},
    )
    bonuses = fields.Float(
        string='Bonuses', states={'done': [('readonly', True)]},
    )
    other_earnings = fields.Float(
        string='Other Earnings', states={'done': [('readonly', True)]},
    )
    total_earnings = fields.Float(
        string='Total Earnings', compute='_compute_totals', store=True,
    )

    # IBC - Ingreso Base de Cotización
    ibc = fields.Float(
        string='IBC', compute='_compute_ibc', store=True,
        help='Ingreso Base de Cotización for social security',
    )

    # Employee deductions
    eps_employee = fields.Float(
        string='EPS Employee (4%)', compute='_compute_deductions', store=True,
    )
    afp_employee = fields.Float(
        string='AFP Employee (4%)', compute='_compute_deductions', store=True,
    )
    solidarity_fund = fields.Float(
        string='Solidarity Fund (1%)', compute='_compute_deductions', store=True,
    )
    withholding_tax = fields.Float(
        string='Withholding Tax', compute='_compute_withholding_tax', store=True,
    )
    manual_deductions = fields.Float(
        string='Manual Deductions', compute='_compute_manual_deductions', store=True,
    )
    loan_deductions = fields.Float(
        string='Loan Deductions', compute='_compute_loan_deductions', store=True,
    )
    total_deductions = fields.Float(
        string='Total Deductions', compute='_compute_totals', store=True,
    )

    # Employer contributions
    eps_employer = fields.Float(
        string='EPS Employer (8.5%)', compute='_compute_employer', store=True,
    )
    afp_employer = fields.Float(
        string='AFP Employer (12%)', compute='_compute_employer', store=True,
    )
    arl_employer = fields.Float(
        string='ARL', compute='_compute_employer', store=True,
    )
    caja_compensacion = fields.Float(
        string='Caja Compensación (4%)', compute='_compute_employer', store=True,
    )
    icbf = fields.Float(
        string='ICBF (3%)', compute='_compute_employer', store=True,
    )
    sena = fields.Float(
        string='SENA (2%)', compute='_compute_employer', store=True,
    )
    total_employer = fields.Float(
        string='Total Employer Contributions',
        compute='_compute_totals', store=True,
    )

    # Provisions
    prima_provision = fields.Float(
        string='Prima Provision', compute='_compute_provisions', store=True,
    )
    cesantias_provision = fields.Float(
        string='Cesantías Provision', compute='_compute_provisions', store=True,
    )
    intereses_cesantias_provision = fields.Float(
        string='Int. Cesantías Provision', compute='_compute_provisions', store=True,
    )
    vacaciones_provision = fields.Float(
        string='Vacaciones Provision', compute='_compute_provisions', store=True,
    )
    total_provisions = fields.Float(
        string='Total Provisions', compute='_compute_totals', store=True,
    )

    # Net pay
    net_pay = fields.Float(
        string='Net Pay', compute='_compute_totals', store=True,
    )

    # Detail lines
    line_ids = fields.One2many(
        'co.payslip.line', 'payslip_id', string='Payslip Lines',
    )

    # Linked records
    overtime_ids = fields.One2many(
        'co.overtime', 'payslip_id', string='Overtime Records',
    )
    deduction_ids = fields.One2many(
        'co.deduction', 'payslip_id', string='Deductions',
    )

    state = fields.Selection([
        ('draft', 'Draft'),
        ('computed', 'Computed'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', tracking=True, required=True)

    company_id = fields.Many2one(
        'res.company', string='Company',
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        related='company_id.currency_id',
    )
    notes = fields.Text(string='Notes')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'co.payslip'
                ) or 'New'
        return super().create(vals_list)

    @api.depends('employee_id')
    def _compute_contract(self):
        for slip in self:
            if slip.employee_id:
                contract = self.env['hr.contract'].search([
                    ('employee_id', '=', slip.employee_id.id),
                    ('state', '=', 'open'),
                ], limit=1)
                slip.contract_id = contract
            else:
                slip.contract_id = False

    @api.depends('contract_id', 'worked_days', 'total_days')
    def _compute_basic_salary(self):
        for slip in self:
            if slip.contract_id and slip.total_days:
                proportion = slip.worked_days / slip.total_days
                slip.basic_salary = round(slip.contract_id.wage * proportion, 0)
                slip.transport_allowance = round(
                    slip.contract_id.co_transport_allowance * proportion, 0
                )
            else:
                slip.basic_salary = 0.0
                slip.transport_allowance = 0.0

    @api.depends('employee_id', 'date_from', 'date_to')
    def _compute_overtime(self):
        for slip in self:
            if slip.employee_id and slip.date_from and slip.date_to:
                overtimes = self.env['co.overtime'].search([
                    ('employee_id', '=', slip.employee_id.id),
                    ('date', '>=', slip.date_from),
                    ('date', '<=', slip.date_to),
                    ('applied', '=', False),
                ])
                slip.overtime_amount = sum(overtimes.mapped('amount'))
            else:
                slip.overtime_amount = 0.0

    @api.depends(
        'basic_salary', 'transport_allowance', 'overtime_amount',
        'commissions', 'bonuses', 'other_earnings',
    )
    def _compute_ibc(self):
        """IBC = earnings excluding transport allowance."""
        for slip in self:
            slip.ibc = (
                slip.basic_salary + slip.overtime_amount
                + slip.commissions + slip.bonuses + slip.other_earnings
            )

    @api.depends('ibc')
    def _compute_deductions(self):
        constants = self.env['co.payroll.constants'].get_current()
        smlmv = constants.smlmv if constants else 1300000
        for slip in self:
            slip.eps_employee = round(slip.ibc * 0.04, 0)
            slip.afp_employee = round(slip.ibc * 0.04, 0)
            # Solidarity fund: >= 4 SMLMV
            if slip.ibc >= (4 * smlmv):
                slip.solidarity_fund = round(slip.ibc * 0.01, 0)
            else:
                slip.solidarity_fund = 0.0

    @api.depends('ibc', 'employee_id')
    def _compute_withholding_tax(self):
        """Compute withholding tax (retención en la fuente) based on UVT table."""
        constants = self.env['co.payroll.constants'].get_current()
        uvt_value = constants.uvt if constants else 47065
        for slip in self:
            if not slip.ibc or not uvt_value:
                slip.withholding_tax = 0.0
                continue
            # Simplified: subtract mandatory deductions, dependents deduction
            taxable_base = slip.ibc - slip.eps_employee - slip.afp_employee
            # Dependents deduction (10% of gross, max 32 UVT/month)
            dependents = self.env['co.family.member'].search_count([
                ('employee_id', '=', slip.employee_id.id),
                ('is_dependent_for_tax', '=', True),
                ('active', '=', True),
            ])
            if dependents > 0:
                dep_deduction = min(taxable_base * 0.10, 32 * uvt_value)
                taxable_base -= dep_deduction
            # Express in UVT
            uvt_income = taxable_base / uvt_value if uvt_value else 0
            # Apply Colombian withholding tax table (Art. 383 ET)
            tax = self._compute_uvt_tax(uvt_income, uvt_value)
            slip.withholding_tax = round(max(tax, 0), 0)

    @api.model
    def _compute_uvt_tax(self, uvt_income, uvt_value):
        """Colombian withholding tax table (Art. 383 Estatuto Tributario).

        Returns the tax amount in COP.
        """
        # Table ranges: (from_uvt, to_uvt, marginal_rate, base_uvt_tax)
        table = [
            (0, 95, 0.0, 0),
            (95, 150, 0.19, 0),
            (150, 360, 0.28, 10.45),
            (360, 640, 0.33, 69.25),
            (640, 945, 0.35, 161.65),
            (945, 2300, 0.37, 268.40),
            (2300, float('inf'), 0.39, 770.15),
        ]
        for from_uvt, to_uvt, rate, base_tax in table:
            if uvt_income <= to_uvt:
                tax_uvt = base_tax + (uvt_income - from_uvt) * rate
                return tax_uvt * uvt_value
        return 0.0

    @api.depends('employee_id', 'date_from', 'date_to')
    def _compute_manual_deductions(self):
        for slip in self:
            if slip.employee_id and slip.date_from and slip.date_to:
                deductions = self.env['co.deduction'].search([
                    ('employee_id', '=', slip.employee_id.id),
                    ('date', '>=', slip.date_from),
                    ('date', '<=', slip.date_to),
                    ('applied', '=', False),
                ])
                slip.manual_deductions = sum(deductions.mapped('amount'))
            else:
                slip.manual_deductions = 0.0

    @api.depends('employee_id')
    def _compute_loan_deductions(self):
        for slip in self:
            if slip.employee_id:
                loans = self.env['co.loan'].search([
                    ('employee_id', '=', slip.employee_id.id),
                    ('state', 'in', ['approved', 'paying']),
                    ('remaining_balance', '>', 0),
                ])
                slip.loan_deductions = sum(
                    min(l.monthly_installment, l.remaining_balance)
                    for l in loans
                )
            else:
                slip.loan_deductions = 0.0

    @api.depends('ibc', 'contract_id')
    def _compute_employer(self):
        constants = self.env['co.payroll.constants'].get_current()
        smlmv = constants.smlmv if constants else 1300000
        for slip in self:
            ibc = slip.ibc
            slip.eps_employer = round(ibc * 0.085, 0)
            slip.afp_employer = round(ibc * 0.12, 0)
            # ARL
            arl_rate = 0.00522  # default Level I
            if slip.contract_id and slip.contract_id.co_arl_risk_level_id:
                arl_rate = slip.contract_id.co_arl_risk_level_id.rate / 100
            slip.arl_employer = round(ibc * arl_rate, 0)
            # Caja
            slip.caja_compensacion = round(ibc * 0.04, 0)
            # ICBF and SENA exemption for employers paying <= 10 SMLMV total payroll
            # Simplified: exempt if employee salary <= 10 SMLMV
            if slip.contract_id and slip.contract_id.wage <= (10 * smlmv):
                slip.icbf = 0.0
                slip.sena = 0.0
            else:
                slip.icbf = round(ibc * 0.03, 0)
                slip.sena = round(ibc * 0.02, 0)

    @api.depends('basic_salary', 'transport_allowance', 'ibc',
                 'worked_days', 'total_days', 'contract_id')
    def _compute_provisions(self):
        """Monthly provisions for prima, cesantías, intereses, vacaciones."""
        for slip in self:
            if not slip.contract_id or not slip.total_days:
                slip.prima_provision = 0.0
                slip.cesantias_provision = 0.0
                slip.intereses_cesantias_provision = 0.0
                slip.vacaciones_provision = 0.0
                continue

            # Base for prima and cesantías includes transport allowance
            base_with_transport = slip.basic_salary + slip.transport_allowance
            # Base for vacaciones does NOT include transport allowance
            base_no_transport = slip.basic_salary

            if slip.contract_id.co_integral_salary:
                # Integral salary: provisions are included in salary (factor 0.70)
                slip.prima_provision = 0.0
                slip.cesantias_provision = 0.0
                slip.intereses_cesantias_provision = 0.0
                slip.vacaciones_provision = 0.0
            else:
                # Prima: 1 salary/year = 8.33% monthly
                slip.prima_provision = round(base_with_transport / 12, 0)
                # Cesantías: 1 salary/year = 8.33% monthly
                slip.cesantias_provision = round(base_with_transport / 12, 0)
                # Intereses cesantías: 12%/year on cesantías = 1% monthly
                slip.intereses_cesantias_provision = round(
                    slip.cesantias_provision * 0.12 / 12, 0
                )
                # Vacaciones: 15 days/year on base salary = 4.17% monthly
                slip.vacaciones_provision = round(base_no_transport * 15 / 360, 0)

    @api.depends(
        'basic_salary', 'transport_allowance', 'overtime_amount',
        'commissions', 'bonuses', 'other_earnings',
        'eps_employee', 'afp_employee', 'solidarity_fund',
        'withholding_tax', 'manual_deductions', 'loan_deductions',
        'eps_employer', 'afp_employer', 'arl_employer',
        'caja_compensacion', 'icbf', 'sena',
        'prima_provision', 'cesantias_provision',
        'intereses_cesantias_provision', 'vacaciones_provision',
    )
    def _compute_totals(self):
        for slip in self:
            slip.total_earnings = (
                slip.basic_salary + slip.transport_allowance
                + slip.overtime_amount + slip.commissions
                + slip.bonuses + slip.other_earnings
            )
            slip.total_deductions = (
                slip.eps_employee + slip.afp_employee
                + slip.solidarity_fund + slip.withholding_tax
                + slip.manual_deductions + slip.loan_deductions
            )
            slip.total_employer = (
                slip.eps_employer + slip.afp_employer
                + slip.arl_employer + slip.caja_compensacion
                + slip.icbf + slip.sena
            )
            slip.total_provisions = (
                slip.prima_provision + slip.cesantias_provision
                + slip.intereses_cesantias_provision
                + slip.vacaciones_provision
            )
            slip.net_pay = slip.total_earnings - slip.total_deductions

    # ---- Actions ----

    def action_compute(self):
        """Compute payslip and generate detail lines."""
        for slip in self:
            if slip.state != 'draft':
                raise UserError('Only draft payslips can be computed.')
            # Trigger recomputation
            slip._compute_basic_salary()
            slip._compute_overtime()
            slip._compute_ibc()
            slip._compute_deductions()
            slip._compute_withholding_tax()
            slip._compute_manual_deductions()
            slip._compute_loan_deductions()
            slip._compute_employer()
            slip._compute_provisions()
            slip._compute_totals()
            # Generate detail lines
            slip._generate_lines()
            slip.write({'state': 'computed'})

    def action_confirm(self):
        """Confirm payslip, mark overtime/deductions as applied, register loan payments."""
        for slip in self:
            if slip.state != 'computed':
                raise UserError('Only computed payslips can be confirmed.')
            # Mark overtime as applied
            if slip.employee_id and slip.date_from and slip.date_to:
                overtimes = self.env['co.overtime'].search([
                    ('employee_id', '=', slip.employee_id.id),
                    ('date', '>=', slip.date_from),
                    ('date', '<=', slip.date_to),
                    ('applied', '=', False),
                ])
                overtimes.write({'applied': True, 'payslip_id': slip.id})
                # Mark deductions as applied
                deductions = self.env['co.deduction'].search([
                    ('employee_id', '=', slip.employee_id.id),
                    ('date', '>=', slip.date_from),
                    ('date', '<=', slip.date_to),
                    ('applied', '=', False),
                ])
                deductions.write({'applied': True, 'payslip_id': slip.id})
            # Register loan payments
            if slip.employee_id:
                loans = self.env['co.loan'].search([
                    ('employee_id', '=', slip.employee_id.id),
                    ('state', 'in', ['approved', 'paying']),
                    ('remaining_balance', '>', 0),
                ])
                for loan in loans:
                    installment = min(
                        loan.monthly_installment, loan.remaining_balance
                    )
                    if installment > 0:
                        loan.register_payment(installment, slip.id)
            slip.write({'state': 'done'})

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_reset_draft(self):
        for slip in self:
            slip.line_ids.unlink()
            # Unmark overtime and deductions
            slip.overtime_ids.write({'applied': False, 'payslip_id': False})
            slip.deduction_ids.write({'applied': False, 'payslip_id': False})
        self.write({'state': 'draft'})

    def _generate_lines(self):
        """Generate payslip detail lines from computed values."""
        self.ensure_one()
        self.line_ids.unlink()
        Line = self.env['co.payslip.line']
        lines_data = [
            # Earnings
            ('BASIC', 'Salario Básico', 'earning', self.basic_salary, 10),
            ('TRANSPORT', 'Auxilio de Transporte', 'earning', self.transport_allowance, 20),
            ('OVERTIME', 'Horas Extra y Recargos', 'earning', self.overtime_amount, 30),
            ('COMMISSIONS', 'Comisiones', 'earning', self.commissions, 40),
            ('BONUSES', 'Bonificaciones', 'earning', self.bonuses, 50),
            ('OTHER_EARN', 'Otros Devengados', 'earning', self.other_earnings, 60),
            # Deductions
            ('EPS_EE', 'EPS Empleado (4%)', 'deduction', self.eps_employee, 100),
            ('AFP_EE', 'AFP Empleado (4%)', 'deduction', self.afp_employee, 110),
            ('SOLIDARITY', 'Fondo de Solidaridad (1%)', 'deduction', self.solidarity_fund, 120),
            ('WITHHOLDING', 'Retención en la Fuente', 'deduction', self.withholding_tax, 130),
            ('MANUAL_DED', 'Deducciones Manuales', 'deduction', self.manual_deductions, 140),
            ('LOAN_DED', 'Descuento Préstamos', 'deduction', self.loan_deductions, 150),
            # Employer
            ('EPS_ER', 'EPS Empleador (8.5%)', 'employer', self.eps_employer, 200),
            ('AFP_ER', 'AFP Empleador (12%)', 'employer', self.afp_employer, 210),
            ('ARL_ER', 'ARL Empleador', 'employer', self.arl_employer, 220),
            ('CAJA', 'Caja Compensación (4%)', 'employer', self.caja_compensacion, 230),
            ('ICBF_ER', 'ICBF (3%)', 'employer', self.icbf, 240),
            ('SENA_ER', 'SENA (2%)', 'employer', self.sena, 250),
            # Provisions
            ('PRIMA', 'Provisión Prima', 'provision', self.prima_provision, 300),
            ('CESANTIAS', 'Provisión Cesantías', 'provision', self.cesantias_provision, 310),
            ('INT_CESANT', 'Provisión Int. Cesantías', 'provision', self.intereses_cesantias_provision, 320),
            ('VACACIONES', 'Provisión Vacaciones', 'provision', self.vacaciones_provision, 330),
        ]
        for code, name, line_type, amount, seq in lines_data:
            if amount:  # Only create non-zero lines
                Line.create({
                    'payslip_id': self.id,
                    'code': code,
                    'name': name,
                    'line_type': line_type,
                    'amount': amount,
                    'sequence': seq,
                })
