from odoo import api, fields, models, _
from odoo.exceptions import UserError


class CoFixedAssetDepreciationLine(models.Model):
    _name = 'co.fixed.asset.depreciation.line'
    _description = 'Fixed Asset Depreciation Line'
    _order = 'date, sequence'

    asset_id = fields.Many2one(
        'co.fixed.asset',
        string='Asset',
        required=True,
        ondelete='cascade',
        index=True,
    )
    sequence = fields.Integer(
        string='#',
        default=10,
    )
    date = fields.Date(
        string='Date',
        required=True,
    )
    amount = fields.Monetary(
        string='Depreciation Amount',
        required=True,
        currency_field='currency_id',
    )
    remaining_value = fields.Monetary(
        string='Remaining Value',
        currency_field='currency_id',
    )
    cumulative_amount = fields.Monetary(
        string='Cumulative Depreciation',
        compute='_compute_cumulative',
        store=True,
        currency_field='currency_id',
    )
    currency_id = fields.Many2one(
        related='asset_id.currency_id',
        store=True,
    )
    move_id = fields.Many2one(
        'account.move',
        string='Journal Entry',
        readonly=True,
        copy=False,
    )
    move_state = fields.Selection(
        related='move_id.state',
        string='Entry Status',
    )

    @api.depends('asset_id.depreciation_line_ids.amount', 'asset_id.depreciation_line_ids.move_id')
    def _compute_cumulative(self):
        for line in self:
            previous = line.asset_id.depreciation_line_ids.filtered(
                lambda l: l.move_id and l.sequence <= line.sequence
            )
            line.cumulative_amount = sum(previous.mapped('amount'))

    def _post_depreciation_entry(self):
        """Create and post a journal entry for this depreciation line."""
        self.ensure_one()
        asset = self.asset_id
        if self.move_id:
            raise UserError(_('This depreciation line already has a journal entry.'))

        move_vals = {
            'journal_id': asset.journal_id.id,
            'date': self.date,
            'ref': _('Depreciation %s - %s (#%s)', asset.code, asset.name, self.sequence),
            'line_ids': [
                (0, 0, {
                    'name': _('Depreciation expense - %s', asset.name),
                    'account_id': asset.expense_account_id.id,
                    'debit': self.amount,
                    'credit': 0.0,
                }),
                (0, 0, {
                    'name': _('Accumulated depreciation - %s', asset.name),
                    'account_id': asset.depreciation_account_id.id,
                    'debit': 0.0,
                    'credit': self.amount,
                }),
            ],
        }
        move = self.env['account.move'].create(move_vals)
        move.action_post()
        self.move_id = move.id
