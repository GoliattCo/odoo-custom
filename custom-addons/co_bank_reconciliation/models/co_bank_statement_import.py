import logging
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class CoBankStatementImport(models.Model):
    _name = 'co.bank.statement.import'
    _description = 'Colombian Bank Statement Import'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_end desc, id desc'

    name = fields.Char(
        string='Name',
        required=True,
        tracking=True,
        default=lambda self: _('New'),
    )
    journal_id = fields.Many2one(
        'account.journal',
        string='Bank Journal',
        required=True,
        domain=[('type', '=', 'bank')],
        tracking=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        related='journal_id.currency_id',
        string='Currency',
        store=True,
    )
    company_currency_id = fields.Many2one(
        related='company_id.currency_id',
        string='Company Currency',
    )
    format_id = fields.Many2one(
        'co.bank.format',
        string='Bank Format',
        required=True,
        tracking=True,
    )
    state = fields.Selection(
        [
            ('draft', 'Draft'),
            ('imported', 'Imported'),
            ('processing', 'Processing'),
            ('reconciled', 'Reconciled'),
            ('done', 'Done'),
            ('cancelled', 'Cancelled'),
        ],
        string='Status',
        default='draft',
        required=True,
        tracking=True,
    )
    date_start = fields.Date(string='Start Date', tracking=True)
    date_end = fields.Date(string='End Date', tracking=True)
    balance_start = fields.Monetary(
        string='Starting Balance',
        currency_field='effective_currency_id',
    )
    balance_end = fields.Monetary(
        string='Ending Balance',
        currency_field='effective_currency_id',
    )
    effective_currency_id = fields.Many2one(
        'res.currency',
        compute='_compute_effective_currency_id',
        string='Effective Currency',
    )

    line_ids = fields.One2many(
        'co.bank.statement.line',
        'statement_id',
        string='Statement Lines',
    )
    line_count = fields.Integer(compute='_compute_line_stats', string='Total Lines')
    reconciled_count = fields.Integer(compute='_compute_line_stats', string='Reconciled')
    unreconciled_count = fields.Integer(compute='_compute_line_stats', string='Unreconciled')
    reconciled_pct = fields.Float(compute='_compute_line_stats', string='Reconciled %')

    # --- Auto-reconciliation settings ---
    match_reference = fields.Boolean(
        string='Match by Reference',
        default=True,
        help='Try to match statement lines to payments/invoices by reference.',
    )
    match_amount = fields.Boolean(
        string='Match by Amount',
        default=True,
        help='Try to match by exact amount.',
    )
    match_date_tolerance = fields.Integer(
        string='Date Tolerance (days)',
        default=3,
        help='Number of days tolerance when matching by date.',
    )
    filename = fields.Char(string='Imported Filename')
    notes = fields.Text(string='Notes')

    @api.depends('journal_id')
    def _compute_effective_currency_id(self):
        for rec in self:
            rec.effective_currency_id = (
                rec.journal_id.currency_id or rec.company_id.currency_id
            )

    @api.depends('line_ids', 'line_ids.reconciled')
    def _compute_line_stats(self):
        for rec in self:
            lines = rec.line_ids
            rec.line_count = len(lines)
            rec.reconciled_count = len(lines.filtered('reconciled'))
            rec.unreconciled_count = rec.line_count - rec.reconciled_count
            rec.reconciled_pct = (
                (rec.reconciled_count / rec.line_count * 100)
                if rec.line_count else 0.0
            )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'co.bank.statement.import'
                ) or _('New')
        return super().create(vals_list)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_auto_reconcile(self):
        """Run auto-reconciliation on all unreconciled lines."""
        self.ensure_one()
        if self.state not in ('imported', 'processing'):
            raise UserError(_('Can only reconcile imported statements.'))
        self.state = 'processing'
        matched = 0
        for line in self.line_ids.filtered(lambda l: not l.reconciled):
            if line._auto_reconcile():
                matched += 1
        if self.unreconciled_count == 0:
            self.state = 'reconciled'
        self.message_post(
            body=_('Auto-reconciliation complete: %d of %d lines matched.') % (
                matched, self.line_count
            ),
        )
        return True

    def action_mark_done(self):
        self.ensure_one()
        self.state = 'done'

    def action_cancel(self):
        self.ensure_one()
        self.line_ids.write({'reconciled': False, 'move_id': False, 'payment_id': False})
        self.state = 'cancelled'

    def action_reset_draft(self):
        self.ensure_one()
        self.line_ids.unlink()
        self.state = 'draft'

    def action_open_lines(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Statement Lines'),
            'res_model': 'co.bank.statement.line',
            'view_mode': 'list,form',
            'domain': [('statement_id', '=', self.id)],
            'context': {'default_statement_id': self.id},
        }

    def action_open_unreconciled(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Unreconciled Lines'),
            'res_model': 'co.bank.statement.line',
            'view_mode': 'list,form',
            'domain': [
                ('statement_id', '=', self.id),
                ('reconciled', '=', False),
            ],
            'context': {'default_statement_id': self.id},
        }
