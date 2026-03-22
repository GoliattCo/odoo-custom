from odoo import fields, models


class CoEpsEntity(models.Model):
    _name = 'co.eps.entity'
    _description = 'EPS Entity'
    _order = 'name'

    name = fields.Char(string='Name', required=True)
    code = fields.Char(string='Code', required=True)
    nit = fields.Char(string='NIT')
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('code_unique', 'UNIQUE(code)', 'EPS code must be unique.'),
    ]
