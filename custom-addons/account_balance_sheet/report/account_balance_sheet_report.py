from odoo import models, fields
from odoo.tools.misc import formatLang


class AccountBalanceSheetReport(models.AbstractModel):
    _name = 'report.account_balance_sheet.account_balance_sheet_document'
    _description = 'Balance Sheet Report'

    def _fmt(self, amount, currency):
        """Format amount: negatives in parentheses, positives plain."""
        formatted = formatLang(self.env, abs(amount), currency_obj=currency)
        return f'({formatted})' if amount < 0 else formatted

    def _get_report_values(self, docids, data=None):
        lines = self.env['account.balance.sheet'].browse(docids)
        currency = self.env.company.currency_id

        # Aggregate debit/credit per class per account
        aggregated = {}  # {class: {account_id: {code, name, debit, credit}}}
        for line in lines.sorted(key=lambda l: (l.account_class or '', l.account_code or '')):
            cls = line.account_class or '?'
            acct_id = line.account_id.id
            if cls not in aggregated:
                aggregated[cls] = {}
            if acct_id not in aggregated[cls]:
                aggregated[cls][acct_id] = {
                    'account_code': line.account_code or '',
                    'account_name': line.account_name or '',
                    'debit': 0.0,
                    'credit': 0.0,
                }
            aggregated[cls][acct_id]['debit'] += line.debit
            aggregated[cls][acct_id]['credit'] += line.credit

        # Build structured sections with sign-flipped displayed saldo
        # Activo (class 1): saldo = debit - credit  (positive = asset)
        # Pasivo (class 2): saldo = credit - debit  (positive = liability)
        # Patrimonio (class 3): saldo = credit - debit  (positive = equity)
        class_labels = {'1': 'ACTIVO', '2': 'PASIVO', '3': 'PATRIMONIO'}
        sections = []
        totals = {'1': 0.0, '2': 0.0, '3': 0.0}

        for cls in ['1', '2', '3']:
            accounts = []
            for acct_data in sorted(
                aggregated.get(cls, {}).values(),
                key=lambda x: x['account_code'],
            ):
                raw = acct_data['debit'] - acct_data['credit']
                saldo = raw if cls == '1' else -raw
                accounts.append({
                    'account_code': acct_data['account_code'],
                    'account_name': acct_data['account_name'],
                    'saldo_fmt': self._fmt(saldo, currency),
                })
                totals[cls] += saldo

            sections.append({
                'class': cls,
                'label': class_labels[cls],
                'accounts': accounts,
                'total_fmt': self._fmt(totals[cls], currency),
            })

        total_pasivo_patrimonio = totals['2'] + totals['3']
        equation_diff = totals['1'] - total_pasivo_patrimonio
        equation_ok = abs(equation_diff) < 0.01

        # "As of" date: max date among the selected lines
        as_of_date = max((l.date for l in lines if l.date), default=fields.Date.today())

        return {
            'doc_ids': docids,
            'sections': sections,
            'total_pasivo_patrimonio_fmt': self._fmt(total_pasivo_patrimonio, currency),
            'equation_diff_fmt': self._fmt(abs(equation_diff), currency),
            'equation_ok': equation_ok,
            'company': self.env.company,
            'user': self.env.user,
            'as_of_date': as_of_date,
            'print_date': fields.Datetime.now(),
        }
