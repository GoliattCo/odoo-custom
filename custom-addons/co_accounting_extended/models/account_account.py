from odoo import fields, models


class AccountAccount(models.Model):
    _inherit = 'account.account'

    requires_cost_center = fields.Boolean(
        string='Requiere Centro de Costo',
        default=False,
        help='Si está marcado, se debe asignar un centro de costo en cada apunte contable que use esta cuenta.',
    )
    requires_item_code = fields.Boolean(
        string='Requiere Código de Ítem',
        default=False,
        help='Si está marcado, se debe asignar un código de ítem en cada apunte contable que use esta cuenta.',
    )
    requires_auxiliar_abierto = fields.Boolean(
        string='Requiere Auxiliar Abierto',
        default=False,
        help='Si está marcado, se debe asignar un valor de auxiliar abierto en cada apunte contable que use esta cuenta.',
    )
