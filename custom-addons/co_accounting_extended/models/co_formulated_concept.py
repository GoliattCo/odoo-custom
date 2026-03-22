import logging

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools.safe_eval import safe_eval

_logger = logging.getLogger(__name__)


class CoFormulatedConcept(models.Model):
    _name = 'co.formulated.concept'
    _description = 'Formulated Concept'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'sequence, name'

    name = fields.Char(
        string='Name',
        required=True,
        tracking=True,
        translate=True,
    )
    code = fields.Char(
        string='Code',
        required=True,
        tracking=True,
    )
    sequence = fields.Integer(string='Sequence', default=10)
    active = fields.Boolean(string='Active', default=True, tracking=True)
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )
    description = fields.Text(string='Description')
    formula = fields.Text(
        string='Formula',
        required=True,
        help=(
            'Python expression that computes a value from account balances.\n\n'
            'Available variables:\n'
            '  balance(prefix) - returns the sum of balances for accounts '
            'whose code starts with the given prefix.\n'
            '  Example: balance("4") - balance("5") - balance("6")\n\n'
            '  account_balance(code) - returns the balance of an exact account code.\n'
            '  abs, round, min, max, sum - standard Python builtins.'
        ),
    )
    display_in_reports = fields.Boolean(
        string='Display in Reports',
        default=True,
        help='Include this concept in printed reports.',
    )
    computed_value = fields.Monetary(
        string='Computed Value',
        currency_field='currency_id',
        compute='_compute_value',
        help='Current computed value based on the formula and posted balances.',
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='company_id.currency_id',
        store=True,
    )

    _sql_constraints = [
        ('code_company_uniq', 'unique(code, company_id)',
         'The code must be unique per company.'),
    ]

    def _get_balance_by_prefix(self, prefix, date_from=None, date_to=None):
        """Return the sum of (credit - debit) for accounts starting with prefix."""
        domain = [
            ('account_id.code', '=like', prefix + '%'),
            ('move_id.state', '=', 'posted'),
            ('company_id', '=', self.company_id.id),
        ]
        if date_from:
            domain.append(('date', '>=', date_from))
        if date_to:
            domain.append(('date', '<=', date_to))

        self.env.cr.execute("""
            SELECT COALESCE(SUM(aml.credit - aml.debit), 0)
            FROM account_move_line aml
            JOIN account_move am ON am.id = aml.move_id
            JOIN account_account aa ON aa.id = aml.account_id
            WHERE aa.code LIKE %s
              AND am.state = 'posted'
              AND aml.company_id = %s
        """, (prefix + '%', self.company_id.id))
        return self.env.cr.fetchone()[0] or 0.0

    def _get_account_balance(self, code, date_from=None, date_to=None):
        """Return the balance (credit - debit) for an exact account code."""
        self.env.cr.execute("""
            SELECT COALESCE(SUM(aml.credit - aml.debit), 0)
            FROM account_move_line aml
            JOIN account_move am ON am.id = aml.move_id
            JOIN account_account aa ON aa.id = aml.account_id
            WHERE aa.code = %s
              AND am.state = 'posted'
              AND aml.company_id = %s
        """, (code, self.company_id.id))
        return self.env.cr.fetchone()[0] or 0.0

    def _evaluate_formula(self, date_from=None, date_to=None):
        """Safely evaluate the formula and return the numeric result."""
        self.ensure_one()
        if not self.formula:
            return 0.0

        local_dict = {
            'balance': lambda prefix: self._get_balance_by_prefix(
                prefix, date_from, date_to
            ),
            'account_balance': lambda code: self._get_account_balance(
                code, date_from, date_to
            ),
            'abs': abs,
            'round': round,
            'min': min,
            'max': max,
            'sum': sum,
        }
        try:
            result = safe_eval(self.formula, local_dict, nocopy=True)
            return float(result)
        except Exception as e:
            _logger.error(
                'Error evaluating formula for concept [%s]: %s', self.code, e
            )
            raise UserError(
                'Error evaluating formula for "%s":\n%s' % (self.name, e)
            ) from e

    @api.depends('formula')
    def _compute_value(self):
        for rec in self:
            try:
                rec.computed_value = rec._evaluate_formula()
            except Exception:
                rec.computed_value = 0.0

    def action_evaluate(self):
        """Button action to trigger recomputation and show result."""
        self.ensure_one()
        value = self._evaluate_formula()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': self.name,
                'message': 'Computed value: {:,.2f}'.format(value),
                'type': 'info',
                'sticky': False,
            },
        }
