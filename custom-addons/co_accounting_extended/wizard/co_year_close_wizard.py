import logging

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class CoYearCloseWizard(models.TransientModel):
    _name = 'co.year.close.wizard'
    _description = 'Year-Close Accounting Entry Wizard'

    fiscal_year = fields.Integer(
        string='Fiscal Year',
        required=True,
        default=lambda self: fields.Date.context_today(self).year - 1,
    )
    date_close = fields.Date(
        string='Closing Date',
        required=True,
        help='Date for the closing journal entry (usually Dec 31).',
    )
    journal_id = fields.Many2one(
        'account.journal',
        string='Closing Journal',
        required=True,
        domain="[('type', '=', 'general')]",
        help='Journal for the year-close entry.',
    )
    pnl_summary_account_id = fields.Many2one(
        'account.account',
        string='P&L Summary Account',
        required=True,
        help=(
            'Temporary account to close income/expense into. '
            'Typically a "Ganancias y Perdidas" summary account.'
        ),
    )
    retained_earnings_account_id = fields.Many2one(
        'account.account',
        string='Retained Earnings Account',
        required=True,
        help='Account to transfer net result. PUC 3605 - Resultados del Ejercicio.',
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )
    move_id = fields.Many2one(
        'account.move',
        string='Generated Entry',
        readonly=True,
    )

    @api.onchange('fiscal_year')
    def _onchange_fiscal_year(self):
        if self.fiscal_year:
            self.date_close = fields.Date.to_date(
                '%d-12-31' % self.fiscal_year
            )

    def _get_account_balances_by_class(self, class_prefix):
        """Get account balances for a PUC class prefix.

        Returns a list of (account_id, account_code, balance) tuples.
        Balance = SUM(debit) - SUM(credit) for the fiscal year.
        """
        date_from = fields.Date.to_date('%d-01-01' % self.fiscal_year)
        date_to = fields.Date.to_date('%d-12-31' % self.fiscal_year)

        self.env.cr.execute("""
            SELECT aa.id, aa.code,
                   COALESCE(SUM(aml.debit) - SUM(aml.credit), 0) AS balance
            FROM account_move_line aml
            JOIN account_move am ON am.id = aml.move_id
            JOIN account_account aa ON aa.id = aml.account_id
            WHERE aa.code LIKE %s
              AND am.state = 'posted'
              AND aml.date >= %s
              AND aml.date <= %s
              AND aml.company_id = %s
            GROUP BY aa.id, aa.code
            HAVING COALESCE(SUM(aml.debit) - SUM(aml.credit), 0) != 0
            ORDER BY aa.code
        """, (class_prefix + '%', date_from, date_to, self.company_id.id))
        return self.env.cr.fetchall()

    def action_generate_year_close(self):
        """Generate the year-close journal entry.

        Steps:
        1. Close income accounts (class 4) -> P&L summary
        2. Close expense accounts (class 5, 6) -> P&L summary
        3. Transfer net result from P&L summary -> retained earnings
        """
        self.ensure_one()

        if not self.journal_id or not self.pnl_summary_account_id:
            raise UserError('Please fill in all required fields.')

        lines = []

        # --- Step 1: Close income accounts (PUC class 4) ---
        # Income accounts normally have credit balances (credit > debit),
        # so balance = debit - credit is typically negative.
        # To close: debit the income account, credit P&L summary.
        income_balances = self._get_account_balances_by_class('4')
        income_total = 0.0
        for account_id, account_code, balance in income_balances:
            # balance = debit - credit; for income this is negative
            # To close, we reverse: debit the income account by |balance|
            lines.append((0, 0, {
                'account_id': account_id,
                'debit': abs(balance) if balance < 0 else 0.0,
                'credit': abs(balance) if balance > 0 else 0.0,
                'name': 'Cierre ingreso %s' % account_code,
            }))
            income_total += balance  # accumulate (negative = net income)

        # --- Step 2: Close expense accounts (PUC class 5, 6) ---
        # Expense accounts normally have debit balances (debit > credit),
        # so balance = debit - credit is typically positive.
        # To close: credit the expense account, debit P&L summary.
        expense_total = 0.0
        for class_prefix in ('5', '6'):
            expense_balances = self._get_account_balances_by_class(class_prefix)
            for account_id, account_code, balance in expense_balances:
                lines.append((0, 0, {
                    'account_id': account_id,
                    'debit': abs(balance) if balance < 0 else 0.0,
                    'credit': abs(balance) if balance > 0 else 0.0,
                    'name': 'Cierre gasto %s' % account_code,
                }))
                expense_total += balance  # accumulate (positive = net expense)

        if not lines:
            raise UserError(
                'No balances found for income/expense accounts in fiscal year %d.'
                % self.fiscal_year
            )

        # P&L summary counterpart for income closings
        # income_total is negative (credit balance) -> P&L summary gets credit
        if income_total:
            lines.append((0, 0, {
                'account_id': self.pnl_summary_account_id.id,
                'debit': abs(income_total) if income_total > 0 else 0.0,
                'credit': abs(income_total) if income_total < 0 else 0.0,
                'name': 'Cierre ingresos a Ganancias y Perdidas',
            }))

        # P&L summary counterpart for expense closings
        # expense_total is positive (debit balance) -> P&L summary gets debit
        if expense_total:
            lines.append((0, 0, {
                'account_id': self.pnl_summary_account_id.id,
                'debit': abs(expense_total) if expense_total < 0 else 0.0,
                'credit': abs(expense_total) if expense_total > 0 else 0.0,
                'name': 'Cierre gastos a Ganancias y Perdidas',
            }))

        # --- Step 3: Transfer net result to retained earnings ---
        # Net result = income_total + expense_total
        # If income > expenses: net_result is negative (net income, credit balance)
        # Transfer: debit P&L summary, credit retained earnings
        net_result = income_total + expense_total  # negative = profit
        if net_result:
            lines.append((0, 0, {
                'account_id': self.pnl_summary_account_id.id,
                'debit': abs(net_result) if net_result < 0 else 0.0,
                'credit': abs(net_result) if net_result > 0 else 0.0,
                'name': 'Transferencia resultado a utilidades retenidas',
            }))
            lines.append((0, 0, {
                'account_id': self.retained_earnings_account_id.id,
                'debit': abs(net_result) if net_result > 0 else 0.0,
                'credit': abs(net_result) if net_result < 0 else 0.0,
                'name': 'Resultado del ejercicio %d' % self.fiscal_year,
            }))

        move = self.env['account.move'].create({
            'journal_id': self.journal_id.id,
            'date': self.date_close,
            'ref': 'Cierre contable %d' % self.fiscal_year,
            'line_ids': lines,
        })

        self.move_id = move.id

        _logger.info(
            'Year-close entry generated: %s with %d lines',
            move.name, len(lines),
        )

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': move.id,
            'view_mode': 'form',
            'target': 'current',
        }
