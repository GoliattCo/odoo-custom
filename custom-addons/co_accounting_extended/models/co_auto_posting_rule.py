import logging

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class CoAutoPostingRule(models.Model):
    _name = 'co.auto.posting.rule'
    _description = 'Automatic Posting Rule'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'sequence, name'

    name = fields.Char(
        string='Name',
        required=True,
        tracking=True,
        translate=True,
    )
    sequence = fields.Integer(string='Sequence', default=10)
    active = fields.Boolean(string='Active', default=True, tracking=True)
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )
    rule_type = fields.Selection(
        [
            ('account_trigger', 'Account Trigger'),
            ('percentage_allocation', 'Percentage Allocation'),
            ('template_recurring', 'Template Recurring'),
        ],
        string='Rule Type',
        required=True,
        default='account_trigger',
        tracking=True,
    )
    description = fields.Text(string='Description')

    # --- Account Trigger fields ---
    trigger_account_id = fields.Many2one(
        'account.account',
        string='Trigger Account',
        help='When this account is debited or credited, the rule fires.',
    )
    trigger_type = fields.Selection(
        [
            ('debit', 'On Debit'),
            ('credit', 'On Credit'),
            ('both', 'On Debit or Credit'),
        ],
        string='Trigger On',
        default='both',
    )
    target_journal_id = fields.Many2one(
        'account.journal',
        string='Target Journal',
        domain="[('type', '=', 'general')]",
        help='Journal where the auto-generated entry will be posted.',
    )
    target_debit_account_id = fields.Many2one(
        'account.account',
        string='Target Debit Account',
    )
    target_credit_account_id = fields.Many2one(
        'account.account',
        string='Target Credit Account',
    )

    # --- Percentage Allocation fields ---
    allocation_line_ids = fields.One2many(
        'co.auto.posting.rule.allocation',
        'rule_id',
        string='Allocation Lines',
    )

    # --- Template Recurring fields ---
    template_journal_id = fields.Many2one(
        'account.journal',
        string='Template Journal',
        domain="[('type', '=', 'general')]",
    )
    template_line_ids = fields.One2many(
        'co.auto.posting.rule.template.line',
        'rule_id',
        string='Template Lines',
    )
    recurring_interval = fields.Integer(
        string='Recurring Interval',
        default=1,
        help='Repeat every X periods.',
    )
    recurring_period = fields.Selection(
        [
            ('daily', 'Day(s)'),
            ('weekly', 'Week(s)'),
            ('monthly', 'Month(s)'),
            ('yearly', 'Year(s)'),
        ],
        string='Recurring Period',
        default='monthly',
    )
    next_execution_date = fields.Date(
        string='Next Execution Date',
    )

    @api.constrains('allocation_line_ids')
    def _check_allocation_total(self):
        for rule in self:
            if rule.rule_type == 'percentage_allocation' and rule.allocation_line_ids:
                total = sum(rule.allocation_line_ids.mapped('percentage'))
                if abs(total - 100.0) > 0.01:
                    raise ValidationError(
                        'The allocation percentages must sum to 100%%. '
                        'Current total: %.2f%%' % total
                    )

    def action_apply_account_trigger(self, source_move_line):
        """Generate a journal entry based on an account trigger rule."""
        self.ensure_one()
        if self.rule_type != 'account_trigger':
            return
        if not self.target_journal_id:
            raise UserError('Target journal is required for account trigger rules.')

        amount = source_move_line.debit or source_move_line.credit
        if not amount:
            return

        move_vals = {
            'journal_id': self.target_journal_id.id,
            'ref': f'Auto: {self.name} - {source_move_line.move_id.name}',
            'line_ids': [
                (0, 0, {
                    'account_id': self.target_debit_account_id.id,
                    'debit': amount,
                    'credit': 0.0,
                    'name': f'Auto-posting: {self.name}',
                    'business_unit_id': source_move_line.business_unit_id.id
                        if source_move_line.business_unit_id else False,
                }),
                (0, 0, {
                    'account_id': self.target_credit_account_id.id,
                    'debit': 0.0,
                    'credit': amount,
                    'name': f'Auto-posting: {self.name}',
                    'business_unit_id': source_move_line.business_unit_id.id
                        if source_move_line.business_unit_id else False,
                }),
            ],
        }
        move = self.env['account.move'].create(move_vals)
        _logger.info('Auto-posting rule [%s] created move %s', self.name, move.name)
        return move

    def action_apply_percentage_allocation(self, source_move_line):
        """Split an amount across cost centers by percentage."""
        self.ensure_one()
        if self.rule_type != 'percentage_allocation':
            return
        if not self.allocation_line_ids:
            raise UserError('Allocation lines are required for percentage allocation rules.')

        amount = source_move_line.debit or source_move_line.credit
        if not amount:
            return

        journal = self.target_journal_id or source_move_line.move_id.journal_id
        lines = []
        total_allocated = 0.0

        for idx, alloc in enumerate(self.allocation_line_ids):
            if idx == len(self.allocation_line_ids) - 1:
                # Last line gets the remainder to avoid rounding issues
                alloc_amount = round(amount - total_allocated, 2)
            else:
                alloc_amount = round(amount * alloc.percentage / 100.0, 2)
                total_allocated += alloc_amount

            analytic_distribution = {}
            if alloc.analytic_account_id:
                analytic_distribution[str(alloc.analytic_account_id.id)] = 100.0

            lines.append((0, 0, {
                'account_id': (alloc.account_id or source_move_line.account_id).id,
                'debit': alloc_amount if source_move_line.debit else 0.0,
                'credit': alloc_amount if source_move_line.credit else 0.0,
                'name': f'Allocation: {self.name} - {alloc.name}',
                'analytic_distribution': analytic_distribution or False,
                'business_unit_id': alloc.business_unit_id.id
                    if alloc.business_unit_id else False,
            }))

        if lines:
            move_vals = {
                'journal_id': journal.id,
                'ref': f'Allocation: {self.name} - {source_move_line.move_id.name}',
                'line_ids': lines,
            }
            move = self.env['account.move'].create(move_vals)
            _logger.info(
                'Percentage allocation rule [%s] created move %s',
                self.name, move.name,
            )
            return move

    def action_generate_recurring_entry(self):
        """Generate journal entries from template for recurring rules."""
        today = fields.Date.context_today(self)
        rules = self.search([
            ('rule_type', '=', 'template_recurring'),
            ('active', '=', True),
            ('next_execution_date', '<=', today),
        ])
        for rule in rules:
            rule._generate_from_template()
            rule._advance_next_execution_date()
        return True

    def _generate_from_template(self):
        """Create a journal entry from template lines."""
        self.ensure_one()
        if not self.template_line_ids:
            _logger.warning('Recurring rule [%s] has no template lines.', self.name)
            return

        journal = self.template_journal_id
        if not journal:
            raise UserError(
                'Template journal is required for recurring rules: %s' % self.name
            )

        lines = []
        for tl in self.template_line_ids:
            lines.append((0, 0, {
                'account_id': tl.account_id.id,
                'debit': tl.debit,
                'credit': tl.credit,
                'name': tl.name or self.name,
                'analytic_distribution': tl.analytic_distribution or False,
                'business_unit_id': tl.business_unit_id.id
                    if tl.business_unit_id else False,
            }))

        move = self.env['account.move'].create({
            'journal_id': journal.id,
            'ref': f'Recurring: {self.name}',
            'date': fields.Date.context_today(self),
            'line_ids': lines,
        })
        _logger.info('Recurring rule [%s] created move %s', self.name, move.name)
        return move

    def _advance_next_execution_date(self):
        """Advance next_execution_date based on recurring interval/period."""
        self.ensure_one()
        from dateutil.relativedelta import relativedelta

        current = self.next_execution_date or fields.Date.context_today(self)
        delta_map = {
            'daily': relativedelta(days=self.recurring_interval),
            'weekly': relativedelta(weeks=self.recurring_interval),
            'monthly': relativedelta(months=self.recurring_interval),
            'yearly': relativedelta(years=self.recurring_interval),
        }
        self.next_execution_date = current + delta_map.get(
            self.recurring_period, relativedelta(months=1)
        )


class CoAutoPostingRuleAllocation(models.Model):
    _name = 'co.auto.posting.rule.allocation'
    _description = 'Auto Posting Rule - Allocation Line'
    _order = 'sequence'

    rule_id = fields.Many2one(
        'co.auto.posting.rule',
        string='Rule',
        required=True,
        ondelete='cascade',
    )
    name = fields.Char(string='Description', required=True)
    sequence = fields.Integer(string='Sequence', default=10)
    percentage = fields.Float(string='Percentage', required=True)
    analytic_account_id = fields.Many2one(
        'account.analytic.account',
        string='Cost Center',
        domain="[('is_cost_center', '=', True)]",
    )
    account_id = fields.Many2one(
        'account.account',
        string='Account',
        help='Override target account. If empty, uses the source account.',
    )
    business_unit_id = fields.Many2one(
        'co.business.unit',
        string='Business Unit',
    )


class CoAutoPostingRuleTemplateLine(models.Model):
    _name = 'co.auto.posting.rule.template.line'
    _description = 'Auto Posting Rule - Template Line'
    _order = 'sequence'

    rule_id = fields.Many2one(
        'co.auto.posting.rule',
        string='Rule',
        required=True,
        ondelete='cascade',
    )
    name = fields.Char(string='Label')
    sequence = fields.Integer(string='Sequence', default=10)
    account_id = fields.Many2one(
        'account.account',
        string='Account',
        required=True,
    )
    debit = fields.Monetary(
        string='Debit',
        currency_field='currency_id',
    )
    credit = fields.Monetary(
        string='Credit',
        currency_field='currency_id',
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='rule_id.company_id.currency_id',
    )
    analytic_distribution = fields.Json(string='Analytic Distribution')
    business_unit_id = fields.Many2one(
        'co.business.unit',
        string='Business Unit',
    )
