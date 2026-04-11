from odoo import fields, models, tools


class CoDashboardBankBalance(models.Model):
    _name = 'co.dashboard.bank.balance'
    _description = 'Bank/Cash Balance'
    _auto = False
    _order = 'balance desc'

    journal_id = fields.Many2one('account.journal', string='Diario', readonly=True)
    journal_name = fields.Char(string='Diario', readonly=True)
    balance = fields.Monetary(string='Saldo', readonly=True)
    company_id = fields.Many2one('res.company', string='Empresa', readonly=True)
    currency_id = fields.Many2one('res.currency', string='Moneda', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    row_number() OVER () AS id,
                    aml.journal_id,
                    aj.name AS journal_name,
                    SUM(aml.debit - aml.credit) AS balance,
                    aml.company_id,
                    aj.currency_id AS currency_id
                FROM account_move_line aml
                JOIN account_journal aj ON aj.id = aml.journal_id
                JOIN account_move am ON am.id = aml.move_id
                WHERE aj.type IN ('bank', 'cash')
                  AND am.state = 'posted'
                GROUP BY aml.journal_id, aj.name, aml.company_id, aj.currency_id
            )
        """ % self._table)
