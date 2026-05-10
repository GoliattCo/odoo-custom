from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = 'account.move'

    debit_credit_difference = fields.Monetary(
        string='Diferencia',
        compute='_compute_debit_credit_difference',
        currency_field='company_currency_id',
        help='Diferencia entre el total de débitos y el total de créditos.',
    )

    @api.depends('line_ids.debit', 'line_ids.credit')
    def _compute_debit_credit_difference(self):
        for move in self:
            total_debit = sum(move.line_ids.mapped('debit'))
            total_credit = sum(move.line_ids.mapped('credit'))
            move.debit_credit_difference = total_debit - total_credit

    def action_export_journal_entry(self):
        """Open the export wizard for this journal entry."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Exportar Asiento Contable'),
            'res_model': 'account.move.export.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_move_id': self.id},
        }

    def action_import_journal_entry(self):
        """Open the import wizard for this journal entry."""
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_('Solo se pueden importar líneas en asientos contables en borrador.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Importar Líneas de Asiento Contable'),
            'res_model': 'account.move.import.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_move_id': self.id},
        }

    def _post(self, soft=True):
        """Override to validate mandatory fields before posting."""
        for move in self:
            for line in move.line_ids:
                if not line.account_id:
                    continue
                account = line.account_id
                if account.requires_cost_center and not line.cost_center_id:
                    raise UserError(_(
                        'La cuenta "%(account)s" requiere un Centro de Costo en la línea "%(label)s" del asiento %(entry)s.',
                        account=account.display_name,
                        label=line.name or '',
                        entry=move.name or _('Nuevo'),
                    ))
                if account.requires_item_code and not line.item_code_id:
                    raise UserError(_(
                        'La cuenta "%(account)s" requiere un Código de Ítem en la línea "%(label)s" del asiento %(entry)s.',
                        account=account.display_name,
                        label=line.name or '',
                        entry=move.name or _('Nuevo'),
                    ))
                if account.requires_auxiliar_abierto and not line.auxiliar_abierto:
                    raise UserError(_(
                        'La cuenta "%(account)s" requiere un Auxiliar Abierto en la línea "%(label)s" del asiento %(entry)s.',
                        account=account.display_name,
                        label=line.name or '',
                        entry=move.name or _('Nuevo'),
                    ))
        return super()._post(soft=soft)
