from odoo import api, fields, models, _
from odoo.exceptions import UserError
from dateutil.relativedelta import relativedelta


class CoBudget(models.Model):
    _name = 'co.budget'
    _description = 'Budget'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_from desc, name'

    name = fields.Char(
        string='Budget Name',
        required=True,
        tracking=True,
        translate=True,
    )
    state = fields.Selection(
        [
            ('draft', 'Draft'),
            ('confirmed', 'Confirmed'),
            ('done', 'Done'),
            ('cancelled', 'Cancelled'),
        ],
        string='State',
        required=True,
        default='draft',
        tracking=True,
        copy=False,
    )
    date_from = fields.Date(
        string='Start Date',
        required=True,
        tracking=True,
    )
    date_to = fields.Date(
        string='End Date',
        required=True,
        tracking=True,
    )
    period_type = fields.Selection(
        [
            ('monthly', 'Monthly'),
            ('quarterly', 'Quarterly'),
            ('yearly', 'Yearly'),
        ],
        string='Period Type',
        required=True,
        default='monthly',
        tracking=True,
        help='How budget lines are distributed across periods.',
    )
    responsible_id = fields.Many2one(
        'res.users',
        string='Responsible',
        default=lambda self: self.env.user,
        tracking=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        tracking=True,
    )
    currency_id = fields.Many2one(
        related='company_id.currency_id',
        string='Currency',
        readonly=True,
        store=True,
    )
    line_ids = fields.One2many(
        'co.budget.line',
        'budget_id',
        string='Budget Lines',
        copy=True,
    )
    active = fields.Boolean(
        string='Active',
        default=True,
    )
    description = fields.Html(
        string='Notes',
    )
    alert_threshold = fields.Float(
        string='Alert Threshold (%)',
        default=80.0,
        tracking=True,
        help='Percentage at which a warning is triggered on budget lines.',
    )
    total_planned = fields.Monetary(
        string='Total Planned',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
    )
    total_actual = fields.Monetary(
        string='Total Actual',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
    )
    total_variance = fields.Monetary(
        string='Total Variance',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
    )
    total_percentage = fields.Float(
        string='Total Executed (%)',
        compute='_compute_totals',
        store=True,
    )

    @api.depends(
        'line_ids.planned_amount',
        'line_ids.actual_amount',
        'line_ids.variance',
    )
    def _compute_totals(self):
        for budget in self:
            lines = budget.line_ids
            budget.total_planned = sum(lines.mapped('planned_amount'))
            budget.total_actual = sum(lines.mapped('actual_amount'))
            budget.total_variance = sum(lines.mapped('variance'))
            if budget.total_planned:
                budget.total_percentage = (
                    budget.total_actual / budget.total_planned
                ) * 100.0
            else:
                budget.total_percentage = 0.0

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for rec in self:
            if rec.date_from and rec.date_to and rec.date_from > rec.date_to:
                raise UserError(_('Start date must be before end date.'))

    def action_confirm(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_('Only draft budgets can be confirmed.'))
            rec.state = 'confirmed'

    def action_done(self):
        for rec in self:
            if rec.state != 'confirmed':
                raise UserError(_('Only confirmed budgets can be marked as done.'))
            rec.state = 'done'

    def action_cancel(self):
        for rec in self:
            if rec.state == 'done':
                raise UserError(_('Done budgets cannot be cancelled.'))
            rec.state = 'cancelled'

    def action_draft(self):
        for rec in self:
            if rec.state != 'cancelled':
                raise UserError(_('Only cancelled budgets can be reset to draft.'))
            rec.state = 'draft'

    def action_compute_actual(self):
        """Recompute actual amounts on all lines."""
        for rec in self:
            rec.line_ids._compute_actual_amount()

    def action_generate_lines(self):
        """Generate budget lines for each period in the budget date range."""
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_('Lines can only be generated on draft budgets.'))

        # Determine period step
        if self.period_type == 'monthly':
            step = relativedelta(months=1)
        elif self.period_type == 'quarterly':
            step = relativedelta(months=3)
        else:
            step = relativedelta(years=1)

        # Gather unique accounts from existing lines or positions
        existing_accounts = self.line_ids.mapped('account_id')
        if not existing_accounts:
            raise UserError(_(
                'Add at least one budget line with an account before '
                'generating period lines.'
            ))

        # Collect planned amounts by account from existing lines
        planned_by_account = {}
        for line in self.line_ids:
            if line.account_id.id not in planned_by_account:
                planned_by_account[line.account_id.id] = {
                    'analytic_account_id': line.analytic_account_id.id,
                    'budget_position_id': line.budget_position_id.id,
                    'planned_amount': line.planned_amount,
                }

        # Remove current lines and regenerate
        self.line_ids.unlink()

        current = self.date_from
        vals_list = []
        while current < self.date_to:
            period_end = min(current + step - relativedelta(days=1), self.date_to)
            for account_id, data in planned_by_account.items():
                vals_list.append({
                    'budget_id': self.id,
                    'account_id': account_id,
                    'analytic_account_id': data['analytic_account_id'],
                    'budget_position_id': data['budget_position_id'],
                    'date_from': current,
                    'date_to': period_end,
                    'planned_amount': data['planned_amount'],
                })
            current = current + step

        if vals_list:
            self.env['co.budget.line'].create(vals_list)
