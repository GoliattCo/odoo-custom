import math
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class CoFixedAsset(models.Model):
    _name = 'co.fixed.asset'
    _description = 'Fixed Asset'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'purchase_date desc, id desc'

    # -- Identification ------------------------------------------------------
    name = fields.Char(
        string='Asset Name',
        required=True,
        tracking=True,
        translate=True,
    )
    code = fields.Char(
        string='Reference',
        readonly=True,
        copy=False,
        default='New',
    )
    serial_number = fields.Char(
        string='Serial Number',
        tracking=True,
    )
    active = fields.Boolean(
        default=True,
    )

    # -- Classification ------------------------------------------------------
    category_id = fields.Many2one(
        'co.fixed.asset.category',
        string='Category',
        required=True,
        tracking=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True,
    )
    currency_id = fields.Many2one(
        related='company_id.currency_id',
        string='Currency',
        store=True,
    )

    # -- Financial -----------------------------------------------------------
    purchase_date = fields.Date(
        string='Purchase Date',
        required=True,
        tracking=True,
        default=fields.Date.context_today,
    )
    purchase_value = fields.Monetary(
        string='Purchase Value',
        required=True,
        tracking=True,
        currency_field='currency_id',
    )
    salvage_value = fields.Monetary(
        string='Salvage Value',
        tracking=True,
        currency_field='currency_id',
    )
    depreciable_value = fields.Monetary(
        string='Depreciable Value',
        compute='_compute_depreciable_value',
        store=True,
        currency_field='currency_id',
    )
    accumulated_depreciation = fields.Monetary(
        string='Accumulated Depreciation',
        compute='_compute_accumulated_depreciation',
        store=True,
        currency_field='currency_id',
    )
    book_value = fields.Monetary(
        string='Book Value',
        compute='_compute_book_value',
        store=True,
        currency_field='currency_id',
    )

    # -- Depreciation settings -----------------------------------------------
    depreciation_method = fields.Selection(
        [
            ('linear', 'Straight-Line'),
            ('degressive', 'Declining Balance'),
        ],
        string='Depreciation Method',
        default='linear',
        required=True,
        tracking=True,
    )
    useful_life = fields.Integer(
        string='Useful Life (Months)',
        required=True,
        default=60,
        tracking=True,
    )
    degressive_factor = fields.Float(
        string='Declining Factor',
        default=2.0,
        help='Multiplier applied to the straight-line rate for declining balance method.',
    )

    # -- Accounting ----------------------------------------------------------
    journal_id = fields.Many2one(
        'account.journal',
        string='Journal',
        domain="[('type', '=', 'general')]",
        tracking=True,
    )
    asset_account_id = fields.Many2one(
        'account.account',
        string='Asset Account',
        tracking=True,
    )
    depreciation_account_id = fields.Many2one(
        'account.account',
        string='Depreciation Account',
        tracking=True,
    )
    expense_account_id = fields.Many2one(
        'account.account',
        string='Expense Account',
        tracking=True,
    )

    # -- Responsibility / Location -------------------------------------------
    responsible_id = fields.Many2one(
        'res.users',
        string='Responsible',
        tracking=True,
        default=lambda self: self.env.user,
    )
    location = fields.Char(
        string='Location',
        tracking=True,
    )
    note = fields.Html(
        string='Notes',
    )

    # -- State ---------------------------------------------------------------
    state = fields.Selection(
        [
            ('draft', 'Draft'),
            ('running', 'Running'),
            ('close', 'Closed'),
            ('disposed', 'Disposed'),
        ],
        string='State',
        default='draft',
        required=True,
        tracking=True,
        copy=False,
    )
    disposal_date = fields.Date(
        string='Disposal Date',
        tracking=True,
    )
    disposal_move_id = fields.Many2one(
        'account.move',
        string='Disposal Entry',
        readonly=True,
        copy=False,
    )

    # -- Relational ----------------------------------------------------------
    depreciation_line_ids = fields.One2many(
        'co.fixed.asset.depreciation.line',
        'asset_id',
        string='Depreciation Lines',
        copy=False,
    )
    maintenance_ids = fields.One2many(
        'co.fixed.asset.maintenance',
        'asset_id',
        string='Maintenance Records',
    )
    depreciation_count = fields.Integer(
        compute='_compute_depreciation_count',
    )
    maintenance_count = fields.Integer(
        compute='_compute_maintenance_count',
    )
    move_count = fields.Integer(
        compute='_compute_move_count',
    )

    # ── Computes ────────────────────────────────────────────────────────────

    @api.depends('purchase_value', 'salvage_value')
    def _compute_depreciable_value(self):
        for rec in self:
            rec.depreciable_value = rec.purchase_value - rec.salvage_value

    @api.depends('depreciation_line_ids.amount', 'depreciation_line_ids.move_id')
    def _compute_accumulated_depreciation(self):
        for rec in self:
            posted = rec.depreciation_line_ids.filtered(lambda l: l.move_id)
            rec.accumulated_depreciation = sum(posted.mapped('amount'))

    @api.depends('purchase_value', 'accumulated_depreciation')
    def _compute_book_value(self):
        for rec in self:
            rec.book_value = rec.purchase_value - rec.accumulated_depreciation

    @api.depends('depreciation_line_ids')
    def _compute_depreciation_count(self):
        for rec in self:
            rec.depreciation_count = len(rec.depreciation_line_ids)

    @api.depends('maintenance_ids')
    def _compute_maintenance_count(self):
        for rec in self:
            rec.maintenance_count = len(rec.maintenance_ids)

    def _compute_move_count(self):
        for rec in self:
            moves = rec.depreciation_line_ids.mapped('move_id')
            if rec.disposal_move_id:
                moves |= rec.disposal_move_id
            rec.move_count = len(moves)

    # ── Onchange / defaults from category ───────────────────────────────────

    @api.onchange('category_id')
    def _onchange_category_id(self):
        if self.category_id:
            cat = self.category_id
            if cat.journal_id:
                self.journal_id = cat.journal_id
            if cat.asset_account_id:
                self.asset_account_id = cat.asset_account_id
            if cat.depreciation_account_id:
                self.depreciation_account_id = cat.depreciation_account_id
            if cat.expense_account_id:
                self.expense_account_id = cat.expense_account_id
            if cat.depreciation_method:
                self.depreciation_method = cat.depreciation_method
            if cat.useful_life:
                self.useful_life = cat.useful_life
            if cat.salvage_percentage and self.purchase_value:
                self.salvage_value = self.purchase_value * cat.salvage_percentage / 100.0

    # ── Constraints ─────────────────────────────────────────────────────────

    @api.constrains('purchase_value')
    def _check_purchase_value(self):
        for rec in self:
            if rec.purchase_value <= 0:
                raise ValidationError(_('Purchase value must be greater than zero.'))

    @api.constrains('salvage_value', 'purchase_value')
    def _check_salvage_value(self):
        for rec in self:
            if rec.salvage_value < 0:
                raise ValidationError(_('Salvage value cannot be negative.'))
            if rec.salvage_value >= rec.purchase_value:
                raise ValidationError(_('Salvage value must be less than purchase value.'))

    @api.constrains('useful_life')
    def _check_useful_life(self):
        for rec in self:
            if rec.useful_life < 1:
                raise ValidationError(_('Useful life must be at least 1 month.'))

    # ── CRUD ────────────────────────────────────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('code', 'New') == 'New':
                vals['code'] = self.env['ir.sequence'].next_by_code('co.fixed.asset') or 'New'
        return super().create(vals_list)

    # ── Workflow actions ────────────────────────────────────────────────────

    def action_confirm(self):
        """Draft -> Running: validate accounts and generate depreciation schedule."""
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_('Only draft assets can be confirmed.'))
            if not rec.journal_id:
                raise UserError(_('Please set a journal before confirming.'))
            if not rec.asset_account_id or not rec.depreciation_account_id or not rec.expense_account_id:
                raise UserError(_('Please set all three accounting accounts before confirming.'))
            rec.state = 'running'
            rec._generate_depreciation_schedule()

    def action_close(self):
        """Running -> Close: mark fully depreciated."""
        for rec in self:
            if rec.state != 'running':
                raise UserError(_('Only running assets can be closed.'))
            rec.state = 'close'

    def action_set_to_draft(self):
        """Reset to draft (only if no posted entries)."""
        for rec in self:
            posted = rec.depreciation_line_ids.filtered(lambda l: l.move_id)
            if posted:
                raise UserError(_(
                    'Cannot reset to draft: there are already posted depreciation entries. '
                    'Please reverse them first.'
                ))
            rec.depreciation_line_ids.unlink()
            rec.state = 'draft'

    def action_dispose(self):
        """Dispose asset: create reversal entry for remaining book value."""
        for rec in self:
            if rec.state not in ('running', 'close'):
                raise UserError(_('Only running or closed assets can be disposed.'))
            if rec.book_value <= 0:
                rec.state = 'disposed'
                rec.disposal_date = fields.Date.context_today(self)
                continue

            move_vals = {
                'journal_id': rec.journal_id.id,
                'date': fields.Date.context_today(self),
                'ref': _('Disposal of %s', rec.name),
                'line_ids': [
                    (0, 0, {
                        'name': _('Disposal - Accumulated Depreciation'),
                        'account_id': rec.depreciation_account_id.id,
                        'debit': rec.accumulated_depreciation,
                        'credit': 0.0,
                    }),
                    (0, 0, {
                        'name': _('Disposal - Loss on Disposal'),
                        'account_id': rec.expense_account_id.id,
                        'debit': rec.book_value,
                        'credit': 0.0,
                    }),
                    (0, 0, {
                        'name': _('Disposal - Asset'),
                        'account_id': rec.asset_account_id.id,
                        'debit': 0.0,
                        'credit': rec.purchase_value,
                    }),
                ],
            }
            move = self.env['account.move'].create(move_vals)
            move.action_post()
            rec.write({
                'state': 'disposed',
                'disposal_date': fields.Date.context_today(self),
                'disposal_move_id': move.id,
            })

    # ── Depreciation schedule generation ────────────────────────────────────

    def _generate_depreciation_schedule(self):
        """Generate the full depreciation schedule (unposted lines)."""
        self.ensure_one()
        self.depreciation_line_ids.filtered(lambda l: not l.move_id).unlink()

        if self.depreciable_value <= 0 or self.useful_life <= 0:
            return

        lines = []
        remaining = self.depreciable_value
        date = self.purchase_date + relativedelta(months=1, day=1)  # first of next month

        if self.depreciation_method == 'linear':
            monthly_amount = self.depreciable_value / self.useful_life
            for i in range(self.useful_life):
                # last period absorbs rounding
                if i == self.useful_life - 1:
                    amount = remaining
                else:
                    amount = round(monthly_amount, 2)
                    remaining -= amount

                lines.append({
                    'asset_id': self.id,
                    'sequence': i + 1,
                    'date': date,
                    'amount': amount,
                    'remaining_value': round(self.depreciable_value - sum(
                        l['amount'] for l in lines
                    ) - amount, 2),
                })
                date += relativedelta(months=1)

        elif self.depreciation_method == 'degressive':
            straight_rate = 1.0 / self.useful_life
            degressive_rate = straight_rate * self.degressive_factor
            for i in range(self.useful_life):
                degressive_amount = remaining * degressive_rate
                linear_amount = remaining / (self.useful_life - i)
                amount = max(degressive_amount, linear_amount)
                amount = round(min(amount, remaining), 2)

                if i == self.useful_life - 1:
                    amount = round(remaining, 2)

                remaining -= amount
                remaining = round(remaining, 2)

                lines.append({
                    'asset_id': self.id,
                    'sequence': i + 1,
                    'date': date,
                    'amount': amount,
                    'remaining_value': remaining,
                })
                date += relativedelta(months=1)

                if remaining <= 0:
                    break

        self.env['co.fixed.asset.depreciation.line'].create(lines)

    # ── Post depreciation entries ───────────────────────────────────────────

    def action_post_depreciation(self):
        """Post all unposted depreciation lines up to today."""
        today = fields.Date.context_today(self)
        for rec in self:
            if rec.state != 'running':
                continue
            unposted = rec.depreciation_line_ids.filtered(
                lambda l: not l.move_id and l.date <= today
            )
            for line in unposted.sorted('date'):
                line._post_depreciation_entry()

            # auto-close if fully depreciated
            if rec.book_value <= rec.salvage_value:
                rec.action_close()

    # ── Cron: monthly auto-depreciation ─────────────────────────────────────

    @api.model
    def _cron_post_depreciation(self):
        """Called by cron to post depreciation entries for all running assets."""
        running = self.search([('state', '=', 'running')])
        running.action_post_depreciation()

    # ── Smart buttons ───────────────────────────────────────────────────────

    def action_view_depreciations(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Depreciation Lines'),
            'res_model': 'co.fixed.asset.depreciation.line',
            'view_mode': 'list,form',
            'domain': [('asset_id', '=', self.id)],
            'context': {'default_asset_id': self.id},
        }

    def action_view_maintenance(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Maintenance'),
            'res_model': 'co.fixed.asset.maintenance',
            'view_mode': 'list,form',
            'domain': [('asset_id', '=', self.id)],
            'context': {'default_asset_id': self.id},
        }

    def action_view_moves(self):
        self.ensure_one()
        move_ids = self.depreciation_line_ids.mapped('move_id').ids
        if self.disposal_move_id:
            move_ids.append(self.disposal_move_id.id)
        return {
            'type': 'ir.actions.act_window',
            'name': _('Journal Entries'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', move_ids)],
        }
