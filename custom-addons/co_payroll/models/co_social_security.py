from odoo import api, fields, models


class CoSocialSecurity(models.Model):
    """Tracks employee social security entity assignments."""
    _name = 'co.social.security'
    _description = 'Employee Social Security Configuration'
    _order = 'employee_id'
    _rec_name = 'employee_id'

    employee_id = fields.Many2one(
        'hr.employee', string='Employee', required=True, ondelete='cascade',
    )
    eps_id = fields.Many2one('co.eps.entity', string='EPS')
    afp_id = fields.Many2one('co.afp.entity', string='AFP (Pension Fund)')
    arl_id = fields.Many2one('co.arl.entity', string='ARL Entity')
    arl_risk_level_id = fields.Many2one(
        'co.arl.risk.level', string='ARL Risk Level',
    )
    caja_compensacion = fields.Char(string='Caja de Compensación')
    date_from = fields.Date(string='Effective From')
    date_to = fields.Date(string='Effective To')
    active = fields.Boolean(default=True)
    notes = fields.Text(string='Notes')

    _sql_constraints = [
        ('employee_unique', 'UNIQUE(employee_id, date_from)',
         'Only one social security record per employee per effective date.'),
    ]
