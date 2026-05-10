from odoo import api, fields, models
from odoo.exceptions import ValidationError


class CoCostCenter(models.Model):
    _name = 'co.cost.center'
    _description = 'Centro de Costo'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'code'
    _parent_name = 'parent_id'
    _parent_store = True
    _rec_name = 'name'
    _rec_names_search = ['name', 'code']

    name = fields.Char(
        string='Descripción',
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
    code_type = fields.Selection(
        [
            ('group', 'Grupo'),
            ('detail', 'Detalle'),
        ],
        string='Tipo de Código',
        required=True,
        default='detail',
        tracking=True,
        help='Los códigos de tipo Grupo son categorías de nivel superior. Los códigos de tipo Detalle son registros de nivel hoja que pueden usarse en transacciones.',
    )
    active = fields.Boolean(string='Activo', default=True, tracking=True)
    company_id = fields.Many2one(
        'res.company',
        string='Empresa',
        required=True,
        default=lambda self: self.env.company,
    )
    parent_id = fields.Many2one(
        'co.cost.center',
        string='Centro de Costo Padre',
        index=True,
        ondelete='restrict',
        domain="[('code_type', '=', 'group')]",
    )
    parent_path = fields.Char(index=True)
    child_ids = fields.One2many(
        'co.cost.center',
        'parent_id',
        string='Centros de Costo Hijos',
    )
    description = fields.Text(string='Notas')

    _code_company_uniq = models.Constraint(
        'unique(code, company_id)',
        'El código del centro de costo debe ser único por empresa.',
    )

    @api.constrains('parent_id')
    def _check_parent_id(self):
        if not self._check_recursion():
            raise ValidationError('Error: No se pueden crear centros de costo recursivos.')

    @api.constrains('code_type', 'child_ids')
    def _check_code_type(self):
        for rec in self:
            if rec.code_type == 'detail' and rec.child_ids:
                raise ValidationError(
                    'Un centro de costo de tipo Detalle no puede tener centros de costo hijos. '
                    'Cambie el tipo a "Grupo" primero.'
                )

    @api.depends('code', 'name')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = f'[{rec.code}] {rec.name}' if rec.code else rec.name
