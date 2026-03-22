from odoo import api, fields, models


class CoOvertime(models.Model):
    """Records overtime hours for payslip calculation.

    Colombian overtime types and surcharges:
    - HED: Hora Extra Diurna (+25%)
    - HEN: Hora Extra Nocturna (+75%)
    - HEDDF: Hora Extra Diurna Dominical/Festiva (+100%)
    - HENDF: Hora Extra Nocturna Dominical/Festiva (+150%)
    - RN: Recargo Nocturno (+35%)
    - RDD: Recargo Dominical/Festivo Diurno (+75%)
    - RDDN: Recargo Dominical/Festivo Nocturno (+110%)
    """
    _name = 'co.overtime'
    _description = 'Overtime Record'
    _order = 'date desc'

    employee_id = fields.Many2one(
        'hr.employee', string='Employee', required=True,
    )
    date = fields.Date(string='Date', required=True)
    overtime_type = fields.Selection([
        ('HED', 'Extra Diurna (HED +25%)'),
        ('HEN', 'Extra Nocturna (HEN +75%)'),
        ('HEDDF', 'Extra Diurna Dom/Fest (HEDDF +100%)'),
        ('HENDF', 'Extra Nocturna Dom/Fest (HENDF +150%)'),
        ('RN', 'Recargo Nocturno (RN +35%)'),
        ('RDD', 'Recargo Dominical Diurno (RDD +75%)'),
        ('RDDN', 'Recargo Dominical Nocturno (RDDN +110%)'),
    ], string='Type', required=True)
    hours = fields.Float(string='Hours', required=True)
    amount = fields.Float(
        string='Amount', compute='_compute_amount', store=True,
    )
    payslip_id = fields.Many2one('co.payslip', string='Payslip')
    applied = fields.Boolean(string='Applied', default=False)
    notes = fields.Text(string='Notes')

    # Surcharge rates (multiplier on hourly rate)
    SURCHARGE_RATES = {
        'HED': 1.25,
        'HEN': 1.75,
        'HEDDF': 2.00,
        'HENDF': 2.50,
        'RN': 0.35,    # surcharge only (base already paid)
        'RDD': 0.75,   # surcharge only
        'RDDN': 1.10,  # surcharge only
    }

    @api.depends('hours', 'overtime_type', 'employee_id')
    def _compute_amount(self):
        for rec in self:
            contract = rec.employee_id.contract_id if rec.employee_id else False
            if contract and rec.hours and rec.overtime_type:
                hourly_rate = contract.wage / 240  # 30 days * 8 hours
                rate = self.SURCHARGE_RATES.get(rec.overtime_type, 1.0)
                rec.amount = round(hourly_rate * rate * rec.hours, 0)
            else:
                rec.amount = 0.0
