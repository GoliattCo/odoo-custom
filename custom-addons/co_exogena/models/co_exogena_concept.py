from odoo import models, fields


class CoExogenaConcept(models.Model):
    """Conceptos DIAN para cada formato de Exogena."""

    _name = 'co.exogena.concept'
    _description = 'Concepto Exogena DIAN'
    _order = 'format_code, code'

    name = fields.Char(
        string='Nombre',
        required=True,
        translate=True,
    )
    code = fields.Char(
        string='Codigo',
        required=True,
        index=True,
    )
    format_code = fields.Selection(
        selection=[
            ('1001', '1001 - Pagos y abonos en cuenta'),
            ('1003', '1003 - Retenciones en la fuente'),
            ('1005', '1005 - IVA descontable'),
            ('1006', '1006 - IVA generado'),
            ('1007', '1007 - Ingresos recibidos'),
            ('1008', '1008 - Cuentas por cobrar'),
            ('1009', '1009 - Cuentas por pagar'),
            ('1010', '1010 - Socios y accionistas'),
            ('1012', '1012 - Declaraciones tributarias'),
        ],
        string='Formato',
        required=True,
        index=True,
    )
    description = fields.Text(
        string='Descripcion',
        translate=True,
    )
    min_amount = fields.Float(
        string='Cuantia minima',
        digits=(16, 2),
        default=0.0,
        help='Monto minimo para reportar en este concepto. 0 = sin minimo.',
    )
    account_ids = fields.Many2many(
        comodel_name='account.account',
        string='Cuentas contables',
        help='Cuentas contables asociadas a este concepto para extraccion automatica.',
    )
    tax_group_id = fields.Many2one(
        comodel_name='account.tax.group',
        string='Grupo de impuestos',
        help='Grupo de impuestos asociado para extraccion automatica.',
    )
    active = fields.Boolean(
        string='Activo',
        default=True,
    )

    _sql_constraints = [
        (
            'format_code_uniq',
            'UNIQUE(format_code, code)',
            'El codigo de concepto debe ser unico por formato.',
        ),
    ]
