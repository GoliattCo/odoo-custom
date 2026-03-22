from odoo import api, fields, models
from odoo.exceptions import UserError


class CoLoan(models.Model):
    _name = 'co.loan'
    _description = 'Employee Loan'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    name = fields.Char(
        string='Reference', required=True, copy=False, readonly=True,
        default='New',
    )
    employee_id = fields.Many2one(
        'hr.employee', string='Employee', required=True, tracking=True,
    )
    loan_date = fields.Date(
        string='Loan Date', required=True, default=fields.Date.today,
    )
    amount = fields.Float(string='Loan Amount', required=True, tracking=True)
    monthly_installment = fields.Float(
        string='Monthly Installment', required=True, tracking=True,
    )
    total_paid = fields.Float(
        string='Total Paid', compute='_compute_totals', store=True,
    )
    remaining_balance = fields.Float(
        string='Remaining Balance', compute='_compute_totals', store=True,
    )
    number_of_installments = fields.Integer(
        string='Number of Installments',
        compute='_compute_number_installments',
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('approved', 'Approved'),
        ('paying', 'In Payment'),
        ('paid', 'Paid'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', tracking=True)
    payment_ids = fields.One2many(
        'co.loan.payment', 'loan_id', string='Payments',
    )
    notes = fields.Text(string='Notes')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'co.loan'
                ) or 'New'
        return super().create(vals_list)

    @api.depends('payment_ids.amount', 'amount')
    def _compute_totals(self):
        for loan in self:
            total_paid = sum(loan.payment_ids.mapped('amount'))
            loan.total_paid = total_paid
            loan.remaining_balance = loan.amount - total_paid

    @api.depends('amount', 'monthly_installment')
    def _compute_number_installments(self):
        for loan in self:
            if loan.monthly_installment > 0:
                import math
                loan.number_of_installments = math.ceil(
                    loan.amount / loan.monthly_installment
                )
            else:
                loan.number_of_installments = 0

    def action_approve(self):
        self.write({'state': 'approved'})

    def action_start_paying(self):
        self.write({'state': 'paying'})

    def action_mark_paid(self):
        self.write({'state': 'paid'})

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_reset_draft(self):
        self.write({'state': 'draft'})

    def register_payment(self, amount, payslip_id=None):
        """Register a payment against this loan, typically from a payslip."""
        self.ensure_one()
        if self.remaining_balance <= 0:
            return 0.0
        actual_amount = min(amount, self.remaining_balance)
        self.env['co.loan.payment'].create({
            'loan_id': self.id,
            'amount': actual_amount,
            'date': fields.Date.today(),
            'payslip_id': payslip_id,
        })
        if self.remaining_balance <= 0:
            self.write({'state': 'paid'})
        elif self.state == 'approved':
            self.write({'state': 'paying'})
        return actual_amount


class CoLoanPayment(models.Model):
    _name = 'co.loan.payment'
    _description = 'Loan Payment'
    _order = 'date desc'

    loan_id = fields.Many2one(
        'co.loan', string='Loan', required=True, ondelete='cascade',
    )
    date = fields.Date(string='Date', required=True, default=fields.Date.today)
    amount = fields.Float(string='Amount', required=True)
    payslip_id = fields.Many2one('co.payslip', string='Payslip')
    notes = fields.Text(string='Notes')
