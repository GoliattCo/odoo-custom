from odoo import api, fields, models


class CoBusinessUnit(models.Model):
    _name = 'co.business.unit'
    _description = 'Unidad de Negocio'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'sequence, name'

    name = fields.Char(
        string='Nombre',
        required=True,
        tracking=True,
        translate=True,
    )
    code = fields.Char(
        string='Código',
        required=True,
        tracking=True,
    )
    sequence = fields.Integer(string='Secuencia', default=10)
    active = fields.Boolean(string='Activo', default=True, tracking=True)
    company_id = fields.Many2one(
        'res.company',
        string='Empresa',
        required=True,
        default=lambda self: self.env.company,
    )
    analytic_account_id = fields.Many2one(
        'account.analytic.account',
        string='Cuenta Analítica',
        tracking=True,
        help='Vincular esta unidad de negocio a una cuenta analítica para reportes.',
    )
    responsible_id = fields.Many2one(
        'res.users',
        string='Responsable',
        tracking=True,
    )
    description = fields.Text(string='Descripción')
    move_line_ids = fields.One2many(
        'account.move.line',
        'business_unit_id',
        string='Apuntes Contables',
    )
    move_line_count = fields.Integer(
        string='Cantidad de Apuntes',
        compute='_compute_move_line_count',
    )

    _code_company_uniq = models.Constraint(
        'unique(code, company_id)',
        'El código debe ser único por empresa.',
    )

    @api.depends('move_line_ids')
    def _compute_move_line_count(self):
        for rec in self:
            rec.move_line_count = len(rec.move_line_ids)

    def name_get(self):
        return [(rec.id, f'[{rec.code}] {rec.name}') for rec in self]
