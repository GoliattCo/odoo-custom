import logging
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class CoBankStatementLine(models.Model):
    _name = 'co.bank.statement.line'
    _description = 'Colombian Bank Statement Line'
    _order = 'date, sequence, id'

    statement_id = fields.Many2one(
        'co.bank.statement.import',
        string='Statement',
        required=True,
        ondelete='cascade',
        index=True,
    )
    journal_id = fields.Many2one(
        related='statement_id.journal_id',
        string='Journal',
        store=True,
    )
    company_id = fields.Many2one(
        related='statement_id.company_id',
        store=True,
    )
    currency_id = fields.Many2one(
        related='statement_id.effective_currency_id',
        store=True,
    )
    sequence = fields.Integer(default=10)

    date = fields.Date(string='Date', required=True, index=True)
    reference = fields.Char(string='Reference', index=True)
    description = fields.Char(string='Description')
    amount = fields.Monetary(
        string='Amount',
        currency_field='currency_id',
        required=True,
        help='Positive = money in (credit to bank in statement), '
             'Negative = money out (debit from bank in statement).',
    )
    balance = fields.Monetary(
        string='Running Balance',
        currency_field='currency_id',
    )

    partner_id = fields.Many2one(
        'res.partner',
        string='Partner',
    )
    reconciled = fields.Boolean(
        string='Reconciled',
        default=False,
        index=True,
    )
    move_id = fields.Many2one(
        'account.move',
        string='Matched Journal Entry',
    )
    payment_id = fields.Many2one(
        'account.payment',
        string='Matched Payment',
    )
    match_type = fields.Selection(
        [
            ('auto_ref', 'Auto: Reference'),
            ('auto_amount', 'Auto: Amount'),
            ('manual', 'Manual'),
        ],
        string='Match Type',
    )
    notes = fields.Text(string='Notes')

    # ------------------------------------------------------------------
    # Auto-reconciliation
    # ------------------------------------------------------------------

    def _auto_reconcile(self):
        """Attempt to auto-reconcile this line. Return True if matched."""
        self.ensure_one()
        stmt = self.statement_id

        # 1. Match by reference against payments
        if stmt.match_reference and self.reference:
            payment = self._match_payment_by_reference()
            if payment:
                self._mark_reconciled_payment(payment, 'auto_ref')
                return True

        # 2. Match by reference against invoices
        if stmt.match_reference and self.reference:
            move = self._match_move_by_reference()
            if move:
                self._mark_reconciled_move(move, 'auto_ref')
                return True

        # 3. Match by amount (+/- date tolerance) against payments
        if stmt.match_amount:
            payment = self._match_payment_by_amount()
            if payment:
                self._mark_reconciled_payment(payment, 'auto_amount')
                return True

        return False

    def _match_payment_by_reference(self):
        """Find a payment whose ref or name contains our reference."""
        self.ensure_one()
        ref = (self.reference or '').strip()
        if not ref:
            return self.env['account.payment']

        domain = [
            ('company_id', '=', self.company_id.id),
            ('journal_id', '=', self.journal_id.id),
            ('state', '=', 'posted'),
            '|',
            ('ref', 'ilike', ref),
            ('name', 'ilike', ref),
        ]
        return self.env['account.payment'].search(domain, limit=1)

    def _match_move_by_reference(self):
        """Find an invoice/bill whose ref or name contains our reference."""
        self.ensure_one()
        ref = (self.reference or '').strip()
        if not ref:
            return self.env['account.move']

        domain = [
            ('company_id', '=', self.company_id.id),
            ('state', '=', 'posted'),
            ('move_type', 'in', ('out_invoice', 'in_invoice', 'out_refund', 'in_refund')),
            '|',
            ('ref', 'ilike', ref),
            ('name', 'ilike', ref),
        ]
        return self.env['account.move'].search(domain, limit=1)

    def _match_payment_by_amount(self):
        """Find a payment matching amount and within date tolerance."""
        self.ensure_one()
        tolerance = self.statement_id.match_date_tolerance
        date_from = self.date - timedelta(days=tolerance)
        date_to = self.date + timedelta(days=tolerance)
        abs_amount = abs(self.amount)

        domain = [
            ('company_id', '=', self.company_id.id),
            ('journal_id', '=', self.journal_id.id),
            ('state', '=', 'posted'),
            ('amount', '=', abs_amount),
            ('date', '>=', date_from),
            ('date', '<=', date_to),
        ]
        return self.env['account.payment'].search(domain, limit=1)

    # ------------------------------------------------------------------
    # Reconciliation helpers
    # ------------------------------------------------------------------

    def _mark_reconciled_payment(self, payment, match_type):
        self.ensure_one()
        self.write({
            'reconciled': True,
            'payment_id': payment.id,
            'partner_id': payment.partner_id.id or self.partner_id.id,
            'match_type': match_type,
        })

    def _mark_reconciled_move(self, move, match_type):
        self.ensure_one()
        self.write({
            'reconciled': True,
            'move_id': move.id,
            'partner_id': move.partner_id.id or self.partner_id.id,
            'match_type': match_type,
        })

    # ------------------------------------------------------------------
    # Manual reconciliation
    # ------------------------------------------------------------------

    def action_manual_reconcile(self):
        """Open a wizard to manually select a journal entry or payment."""
        self.ensure_one()
        if self.reconciled:
            raise UserError(_('This line is already reconciled.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Manual Reconciliation'),
            'res_model': 'co.bank.statement.line',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_unreconcile(self):
        """Remove reconciliation from this line."""
        self.ensure_one()
        self.write({
            'reconciled': False,
            'move_id': False,
            'payment_id': False,
            'match_type': False,
        })

    def action_open_matched_entry(self):
        """Open the matched journal entry or payment."""
        self.ensure_one()
        if self.payment_id:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'account.payment',
                'res_id': self.payment_id.id,
                'view_mode': 'form',
                'target': 'current',
            }
        if self.move_id:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'account.move',
                'res_id': self.move_id.id,
                'view_mode': 'form',
                'target': 'current',
            }
        raise UserError(_('No matched entry found.'))
