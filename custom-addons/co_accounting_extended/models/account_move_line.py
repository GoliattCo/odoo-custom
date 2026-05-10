from odoo import api, fields, models


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    business_unit_id = fields.Many2one(
        'co.business.unit',
        string='Unidad de Negocio',
        index=True,
        help='Unidad de negocio asociada a este apunte contable.',
    )
    cost_center_id = fields.Many2one(
        'co.cost.center',
        string='Centro de Costo',
        index=True,
        domain="[('code_type', '=', 'detail')]",
        help='Centro de costo asociado a este apunte contable.',
    )
    item_code_id = fields.Many2one(
        'co.item.code',
        string='Código de Ítem',
        index=True,
        domain="[('code_type', '=', 'detail')]",
        help='Código de ítem asociado a este apunte contable.',
    )
    auxiliar_abierto = fields.Char(
        string='Auxiliar Abierto',
        help='Valor de auxiliar abierto para este apunte contable.',
    )
    concepto_contable_id = fields.Many2one(
        'co.accounting.concept',
        string='Concepto Contable',
        index=True,
        help='Al seleccionar un concepto contable, la cuenta se asignará automáticamente desde el concepto.',
    )
    cost_center_notes = fields.Char(
        string='Notas Centro de Costo',
        help='Notas adicionales relacionadas con la asignación del centro de costo.',
    )

    @api.onchange('concepto_contable_id')
    def _onchange_concepto_contable_id(self):
        if self.concepto_contable_id and self.concepto_contable_id.account_id:
            self.account_id = self.concepto_contable_id.account_id
