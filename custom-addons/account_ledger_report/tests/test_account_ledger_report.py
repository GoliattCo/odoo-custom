from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('account_ledger_report', 'post_install', '-at_install')
class TestAccountLedgerReport(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref('base.main_company')
        cls.journal = cls.env['account.journal'].search([
            ('type', '=', 'general'),
            ('company_id', '=', cls.company.id),
        ], limit=1)
        cls.account_receivable = cls.env['account.account'].search([
            ('account_type', '=', 'asset_receivable'),
            ('company_ids', 'in', cls.company.id),
        ], limit=1)
        cls.account_revenue = cls.env['account.account'].search([
            ('account_type', '=', 'income'),
            ('company_ids', 'in', cls.company.id),
        ], limit=1)

    def _create_posted_move(self, date, debit_account, credit_account, amount):
        move = self.env['account.move'].create({
            'journal_id': self.journal.id,
            'date': date,
            'line_ids': [
                (0, 0, {
                    'account_id': debit_account.id,
                    'debit': amount,
                    'credit': 0.0,
                }),
                (0, 0, {
                    'account_id': credit_account.id,
                    'debit': 0.0,
                    'credit': amount,
                }),
            ],
        })
        move.action_post()
        return move

    def test_posted_entries_appear(self):
        """Posted journal entries must appear in the report."""
        move = self._create_posted_move(
            '2026-01-15', self.account_receivable, self.account_revenue, 100.0
        )
        lines = self.env['account.ledger.report'].search([('move_id', '=', move.id)])
        self.assertEqual(len(lines), 2)
        debit_line = lines.filtered(lambda l: l.debit == 100.0)
        self.assertEqual(len(debit_line), 1)
        self.assertEqual(debit_line.account_id, self.account_receivable)

    def test_draft_entries_excluded(self):
        """Draft entries must NOT appear in the report."""
        move = self.env['account.move'].create({
            'journal_id': self.journal.id,
            'date': '2026-01-15',
            'line_ids': [
                (0, 0, {
                    'account_id': self.account_receivable.id,
                    'debit': 50.0,
                    'credit': 0.0,
                }),
                (0, 0, {
                    'account_id': self.account_revenue.id,
                    'debit': 0.0,
                    'credit': 50.0,
                }),
            ],
        })
        # deliberately NOT posting the move
        lines = self.env['account.ledger.report'].search([('move_id', '=', move.id)])
        self.assertEqual(len(lines), 0, "Draft entries must not appear")

    def test_account_code_populated(self):
        """account_code must come from the SQL SELECT (not ORM related)."""
        move = self._create_posted_move(
            '2026-01-15', self.account_receivable, self.account_revenue, 200.0
        )
        lines = self.env['account.ledger.report'].search([('move_id', '=', move.id)])
        for line in lines:
            self.assertTrue(line.account_code, "account_code must be populated from SQL")

    def test_date_filter(self):
        """Date range filter must work correctly."""
        move = self._create_posted_move(
            '2026-02-15', self.account_receivable, self.account_revenue, 75.0
        )
        lines = self.env['account.ledger.report'].search([
            ('move_id', '=', move.id),
            ('date', '>=', '2026-02-01'),
            ('date', '<=', '2026-02-28'),
        ])
        self.assertEqual(len(lines), 2)

    def test_debit_credit_values(self):
        """Debit and credit values must match the journal entry lines."""
        move = self._create_posted_move(
            '2026-01-20', self.account_receivable, self.account_revenue, 300.0
        )
        lines = self.env['account.ledger.report'].search([('move_id', '=', move.id)])
        total_debit = sum(lines.mapped('debit'))
        total_credit = sum(lines.mapped('credit'))
        self.assertEqual(total_debit, 300.0)
        self.assertEqual(total_credit, 300.0)
