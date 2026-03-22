from odoo import api, fields, models
from odoo.exceptions import UserError


class CoPila(models.Model):
    """PILA - Planilla Integrada de Liquidación de Aportes.

    Monthly social security contribution filing.
    """
    _name = 'co.pila'
    _description = 'PILA (Social Security Filing)'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'period_year desc, period_month desc'

    name = fields.Char(
        string='Reference', compute='_compute_name', store=True,
    )
    period_month = fields.Selection([
        ('01', 'January'), ('02', 'February'), ('03', 'March'),
        ('04', 'April'), ('05', 'May'), ('06', 'June'),
        ('07', 'July'), ('08', 'August'), ('09', 'September'),
        ('10', 'October'), ('11', 'November'), ('12', 'December'),
    ], string='Month', required=True, tracking=True)
    period_year = fields.Integer(
        string='Year', required=True,
        default=lambda self: fields.Date.today().year,
    )
    company_id = fields.Many2one(
        'res.company', string='Company',
        default=lambda self: self.env.company,
    )
    line_ids = fields.One2many(
        'co.pila.line', 'pila_id', string='Employee Lines',
    )
    total_eps_employee = fields.Float(
        string='Total EPS Employee', compute='_compute_totals', store=True,
    )
    total_eps_employer = fields.Float(
        string='Total EPS Employer', compute='_compute_totals', store=True,
    )
    total_afp_employee = fields.Float(
        string='Total AFP Employee', compute='_compute_totals', store=True,
    )
    total_afp_employer = fields.Float(
        string='Total AFP Employer', compute='_compute_totals', store=True,
    )
    total_arl = fields.Float(
        string='Total ARL', compute='_compute_totals', store=True,
    )
    total_caja = fields.Float(
        string='Total Caja', compute='_compute_totals', store=True,
    )
    total_icbf = fields.Float(
        string='Total ICBF', compute='_compute_totals', store=True,
    )
    total_sena = fields.Float(
        string='Total SENA', compute='_compute_totals', store=True,
    )
    total_solidarity = fields.Float(
        string='Total Solidarity Fund', compute='_compute_totals', store=True,
    )
    grand_total = fields.Float(
        string='Grand Total', compute='_compute_totals', store=True,
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('generated', 'Generated'),
        ('filed', 'Filed'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', tracking=True)

    @api.depends('period_month', 'period_year')
    def _compute_name(self):
        for rec in self:
            month_name = dict(rec._fields['period_month'].selection).get(
                rec.period_month, ''
            )
            rec.name = f"PILA {month_name} {rec.period_year}"

    @api.depends('line_ids.eps_employee', 'line_ids.eps_employer',
                 'line_ids.afp_employee', 'line_ids.afp_employer',
                 'line_ids.arl', 'line_ids.caja', 'line_ids.icbf',
                 'line_ids.sena', 'line_ids.solidarity_fund')
    def _compute_totals(self):
        for rec in self:
            lines = rec.line_ids
            rec.total_eps_employee = sum(lines.mapped('eps_employee'))
            rec.total_eps_employer = sum(lines.mapped('eps_employer'))
            rec.total_afp_employee = sum(lines.mapped('afp_employee'))
            rec.total_afp_employer = sum(lines.mapped('afp_employer'))
            rec.total_arl = sum(lines.mapped('arl'))
            rec.total_caja = sum(lines.mapped('caja'))
            rec.total_icbf = sum(lines.mapped('icbf'))
            rec.total_sena = sum(lines.mapped('sena'))
            rec.total_solidarity = sum(lines.mapped('solidarity_fund'))
            rec.grand_total = (
                rec.total_eps_employee + rec.total_eps_employer
                + rec.total_afp_employee + rec.total_afp_employer
                + rec.total_arl + rec.total_caja
                + rec.total_icbf + rec.total_sena
                + rec.total_solidarity
            )

    def action_generate(self):
        """Generate PILA lines from confirmed payslips for the period."""
        for pila in self:
            if pila.state != 'draft':
                raise UserError('Only draft PILA records can be generated.')
            pila.line_ids.unlink()
            # Find payslips for the period
            year = pila.period_year
            month = int(pila.period_month)
            payslips = self.env['co.payslip'].search([
                ('state', '=', 'done'),
                ('date_from', '>=', f'{year}-{month:02d}-01'),
                ('date_from', '<=', f'{year}-{month:02d}-28'),
                ('company_id', '=', pila.company_id.id),
            ])
            for slip in payslips:
                self.env['co.pila.line'].create({
                    'pila_id': pila.id,
                    'employee_id': slip.employee_id.id,
                    'payslip_id': slip.id,
                    'ibc': slip.ibc,
                    'eps_employee': slip.eps_employee,
                    'eps_employer': slip.eps_employer,
                    'afp_employee': slip.afp_employee,
                    'afp_employer': slip.afp_employer,
                    'arl': slip.arl_employer,
                    'caja': slip.caja_compensacion,
                    'icbf': slip.icbf,
                    'sena': slip.sena,
                    'solidarity_fund': slip.solidarity_fund,
                })
            pila.write({'state': 'generated'})

    def action_file(self):
        self.write({'state': 'filed'})

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_reset_draft(self):
        for pila in self:
            pila.line_ids.unlink()
        self.write({'state': 'draft'})


class CoPilaLine(models.Model):
    _name = 'co.pila.line'
    _description = 'PILA Line'
    _order = 'employee_id'

    pila_id = fields.Many2one(
        'co.pila', string='PILA', required=True, ondelete='cascade',
    )
    employee_id = fields.Many2one(
        'hr.employee', string='Employee', required=True,
    )
    payslip_id = fields.Many2one('co.payslip', string='Payslip')
    ibc = fields.Float(string='IBC')
    eps_employee = fields.Float(string='EPS Employee')
    eps_employer = fields.Float(string='EPS Employer')
    afp_employee = fields.Float(string='AFP Employee')
    afp_employer = fields.Float(string='AFP Employer')
    arl = fields.Float(string='ARL')
    caja = fields.Float(string='Caja')
    icbf = fields.Float(string='ICBF')
    sena = fields.Float(string='SENA')
    solidarity_fund = fields.Float(string='Solidarity Fund')
    total = fields.Float(string='Total', compute='_compute_total', store=True)

    @api.depends(
        'eps_employee', 'eps_employer', 'afp_employee', 'afp_employer',
        'arl', 'caja', 'icbf', 'sena', 'solidarity_fund',
    )
    def _compute_total(self):
        for line in self:
            line.total = (
                line.eps_employee + line.eps_employer
                + line.afp_employee + line.afp_employer
                + line.arl + line.caja + line.icbf + line.sena
                + line.solidarity_fund
            )
