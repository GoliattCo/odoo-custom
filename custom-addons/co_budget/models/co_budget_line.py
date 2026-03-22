from odoo import api, fields, models, _
from odoo.exceptions import UserError


class CoBudgetLine(models.Model):
    _name = 'co.budget.line'
    _description = 'Budget Line'
    _order = 'date_from, account_id'

    budget_id = fields.Many2one(
        'co.budget',
        string='Budget',
        required=True,
        ondelete='cascade',
        index=True,
    )
    budget_state = fields.Selection(
        related='budget_id.state',
        string='Budget State',
        store=True,
    )
    company_id = fields.Many2one(
        related='budget_id.company_id',
        string='Company',
        store=True,
    )
    currency_id = fields.Many2one(
        related='budget_id.currency_id',
        string='Currency',
        store=True,
    )
    account_id = fields.Many2one(
        'account.account',
        string='Account',
        required=True,
        index=True,
    )
    analytic_account_id = fields.Many2one(
        'account.analytic.account',
        string='Analytic Account',
        index=True,
    )
    budget_position_id = fields.Many2one(
        'co.budget.position',
        string='Budget Position',
        index=True,
    )
    date_from = fields.Date(
        string='Start Date',
        required=True,
    )
    date_to = fields.Date(
        string='End Date',
        required=True,
    )
    planned_amount = fields.Monetary(
        string='Planned Amount',
        required=True,
        currency_field='currency_id',
        default=0.0,
    )
    actual_amount = fields.Monetary(
        string='Actual Amount',
        compute='_compute_actual_amount',
        store=True,
        currency_field='currency_id',
    )
    variance = fields.Monetary(
        string='Variance',
        compute='_compute_variance',
        store=True,
        currency_field='currency_id',
        help='Planned minus Actual. Positive = under budget.',
    )
    percentage = fields.Float(
        string='Executed (%)',
        compute='_compute_variance',
        store=True,
    )
    alert_level = fields.Selection(
        [
            ('ok', 'OK'),
            ('warning', 'Warning'),
            ('exceeded', 'Exceeded'),
        ],
        string='Alert',
        compute='_compute_alert_level',
        store=True,
    )

    @api.depends(
        'account_id',
        'analytic_account_id',
        'date_from',
        'date_to',
        'budget_id.company_id',
        'budget_id.state',
    )
    def _compute_actual_amount(self):
        """Compute actual amount from posted journal entries."""
        for line in self:
            if not line.account_id or not line.date_from or not line.date_to:
                line.actual_amount = 0.0
                continue

            domain = [
                ('account_id', '=', line.account_id.id),
                ('date', '>=', line.date_from),
                ('date', '<=', line.date_to),
                ('parent_state', '=', 'posted'),
                ('company_id', '=', line.company_id.id),
            ]

            # Filter by analytic account if set
            # In Odoo 18, analytic_distribution is a JSON field
            # We query move lines and filter in Python for analytic
            move_lines = self.env['account.move.line'].search(domain)

            if line.analytic_account_id:
                analytic_id = str(line.analytic_account_id.id)
                filtered = move_lines.filtered(
                    lambda ml: ml.analytic_distribution
                    and analytic_id in ml.analytic_distribution
                )
                # Sum weighted by distribution percentage
                total = 0.0
                for ml in filtered:
                    pct = ml.analytic_distribution.get(analytic_id, 0)
                    total += (ml.debit - ml.credit) * pct / 100.0
                line.actual_amount = abs(total)
            else:
                line.actual_amount = abs(
                    sum(move_lines.mapped('debit'))
                    - sum(move_lines.mapped('credit'))
                )

    @api.depends('planned_amount', 'actual_amount')
    def _compute_variance(self):
        for line in self:
            line.variance = line.planned_amount - line.actual_amount
            if line.planned_amount:
                line.percentage = (
                    line.actual_amount / line.planned_amount
                ) * 100.0
            else:
                line.percentage = 0.0

    @api.depends('percentage', 'budget_id.alert_threshold')
    def _compute_alert_level(self):
        for line in self:
            threshold = line.budget_id.alert_threshold or 80.0
            if line.percentage >= 100.0:
                line.alert_level = 'exceeded'
            elif line.percentage >= threshold:
                line.alert_level = 'warning'
            else:
                line.alert_level = 'ok'

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for rec in self:
            if rec.date_from and rec.date_to and rec.date_from > rec.date_to:
                raise UserError(_('Start date must be before end date.'))

    @api.onchange('budget_position_id')
    def _onchange_budget_position_id(self):
        """Restrict account domain to position accounts when set."""
        if self.budget_position_id and self.budget_position_id.account_ids:
            return {
                'domain': {
                    'account_id': [
                        ('id', 'in', self.budget_position_id.account_ids.ids)
                    ]
                }
            }
        return {'domain': {'account_id': []}}

    @api.onchange('budget_id')
    def _onchange_budget_id(self):
        """Default dates from parent budget."""
        if self.budget_id:
            if not self.date_from:
                self.date_from = self.budget_id.date_from
            if not self.date_to:
                self.date_to = self.budget_id.date_to
