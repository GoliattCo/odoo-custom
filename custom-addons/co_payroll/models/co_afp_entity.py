from odoo import fields, models


class CoAfpEntity(models.Model):
    _name = 'co.afp.entity'
    _description = 'AFP Entity (Pension Fund)'
    _order = 'name'

    name = fields.Char(string='Name', required=True)
    code = fields.Char(string='Code', required=True)
    nit = fields.Char(string='NIT')
    fund_type = fields.Selection([
        ('private', 'Private Fund'),
        ('public', 'Colpensiones'),
    ], string='Fund Type', default='private')
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('code_unique', 'UNIQUE(code)', 'AFP code must be unique.'),
    ]
