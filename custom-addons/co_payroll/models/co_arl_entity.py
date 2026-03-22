from odoo import fields, models


class CoArlEntity(models.Model):
    _name = 'co.arl.entity'
    _description = 'ARL Entity'
    _order = 'name'

    name = fields.Char(string='Name', required=True)
    code = fields.Char(string='Code', required=True)
    nit = fields.Char(string='NIT')
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('code_unique', 'UNIQUE(code)', 'ARL code must be unique.'),
    ]


class CoArlRiskLevel(models.Model):
    _name = 'co.arl.risk.level'
    _description = 'ARL Risk Level'
    _order = 'level'

    name = fields.Char(string='Name', required=True)
    level = fields.Selection([
        ('I', 'Level I - Minimum Risk'),
        ('II', 'Level II - Low Risk'),
        ('III', 'Level III - Medium Risk'),
        ('IV', 'Level IV - High Risk'),
        ('V', 'Level V - Maximum Risk'),
    ], string='Risk Level', required=True)
    rate = fields.Float(
        string='Rate (%)', required=True, digits=(5, 3),
        help='ARL contribution rate as a percentage',
    )

    _sql_constraints = [
        ('level_unique', 'UNIQUE(level)', 'Each risk level must be unique.'),
    ]
