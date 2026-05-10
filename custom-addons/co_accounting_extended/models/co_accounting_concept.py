from odoo import api, fields, models


class CoAccountingConcept(models.Model):
    _name = 'co.accounting.concept'
    _description = 'Concepto Contable'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'code'
    _rec_name = 'name'
    _rec_names_search = ['name', 'code']

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
        index=True,
    )
    account_id = fields.Many2one(
        'account.account',
        string='Cuenta Contable',
        required=True,
        tracking=True,
        help='Cuenta del plan contable asociada a este concepto. Se asignará automáticamente al seleccionar este concepto en un asiento contable.',
    )
    active = fields.Boolean(string='Activo', default=True, tracking=True)
    company_id = fields.Many2one(
        'res.company',
        string='Empresa',
        required=True,
        default=lambda self: self.env.company,
    )
    description = fields.Text(string='Descripción')

    _code_company_uniq = models.Constraint(
        'unique(code, company_id)',
        'El código del concepto contable debe ser único por empresa.',
    )

    @api.depends('code', 'name')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = f'[{rec.code}] {rec.name}' if rec.code else rec.name
