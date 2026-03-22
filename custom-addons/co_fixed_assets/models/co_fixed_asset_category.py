from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class CoFixedAssetCategory(models.Model):
    _name = 'co.fixed.asset.category'
    _description = 'Fixed Asset Category'
    _order = 'name'

    name = fields.Char(
        string='Category Name',
        required=True,
        translate=True,
    )
    code = fields.Char(
        string='Code',
    )
    active = fields.Boolean(
        default=True,
    )

    # -- Default accounting --------------------------------------------------
    journal_id = fields.Many2one(
        'account.journal',
        string='Journal',
        domain="[('type', '=', 'general')]",
        help='Default journal for depreciation entries.',
    )
    asset_account_id = fields.Many2one(
        'account.account',
        string='Asset Account',
        help='Account where the asset value is recorded (debit on purchase).',
    )
    depreciation_account_id = fields.Many2one(
        'account.account',
        string='Depreciation Account',
        help='Account for accumulated depreciation (credit on depreciation).',
    )
    expense_account_id = fields.Many2one(
        'account.account',
        string='Expense Account',
        help='Expense account for depreciation charges (debit on depreciation).',
    )

    # -- Default depreciation settings ---------------------------------------
    depreciation_method = fields.Selection(
        [
            ('linear', 'Straight-Line'),
            ('degressive', 'Declining Balance'),
        ],
        string='Depreciation Method',
        default='linear',
    )
    useful_life = fields.Integer(
        string='Useful Life (Months)',
        default=60,
    )
    salvage_percentage = fields.Float(
        string='Salvage Value (%)',
        default=0.0,
        help='Default salvage value as percentage of purchase value.',
    )

    # -- Relational ----------------------------------------------------------
    asset_ids = fields.One2many(
        'co.fixed.asset',
        'category_id',
        string='Assets',
    )
    asset_count = fields.Integer(
        string='Asset Count',
        compute='_compute_asset_count',
    )

    @api.depends('asset_ids')
    def _compute_asset_count(self):
        for rec in self:
            rec.asset_count = len(rec.asset_ids)

    @api.constrains('useful_life')
    def _check_useful_life(self):
        for rec in self:
            if rec.useful_life and rec.useful_life < 1:
                raise ValidationError(_('Useful life must be at least 1 month.'))

    @api.constrains('salvage_percentage')
    def _check_salvage_percentage(self):
        for rec in self:
            if rec.salvage_percentage < 0 or rec.salvage_percentage > 100:
                raise ValidationError(_('Salvage percentage must be between 0 and 100.'))

    def action_view_assets(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Assets'),
            'res_model': 'co.fixed.asset',
            'view_mode': 'list,form',
            'domain': [('category_id', '=', self.id)],
            'context': {'default_category_id': self.id},
        }
