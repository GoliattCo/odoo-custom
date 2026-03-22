from odoo import api, fields, models


class AccountAnalyticAccount(models.Model):
    _inherit = 'account.analytic.account'

    is_cost_center = fields.Boolean(
        string='Is Cost Center',
        default=False,
        help='Mark this analytic account as a cost center.',
    )
    cost_center_parent_id = fields.Many2one(
        'account.analytic.account',
        string='Parent Cost Center',
        domain="[('is_cost_center', '=', True)]",
        help='Hierarchical parent cost center.',
    )
    cost_center_child_ids = fields.One2many(
        'account.analytic.account',
        'cost_center_parent_id',
        string='Child Cost Centers',
    )
    responsible_id = fields.Many2one(
        'res.users',
        string='Responsible',
        help='Person responsible for this cost center.',
    )
    budget_allocated = fields.Monetary(
        string='Budget Allocated',
        currency_field='currency_id',
        help='Annual budget allocated to this cost center.',
    )
    budget_consumed = fields.Monetary(
        string='Budget Consumed',
        currency_field='currency_id',
        compute='_compute_budget_consumed',
        help='Total amount consumed from the allocated budget.',
    )
    budget_remaining = fields.Monetary(
        string='Budget Remaining',
        currency_field='currency_id',
        compute='_compute_budget_consumed',
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='company_id.currency_id',
        store=True,
    )
    cost_center_notes = fields.Text(string='Cost Center Notes')

    @api.depends('budget_allocated')
    def _compute_budget_consumed(self):
        """Compute consumed budget from posted journal items linked to this analytic account."""
        for rec in self:
            if not rec.is_cost_center or not rec.id:
                rec.budget_consumed = 0.0
                rec.budget_remaining = rec.budget_allocated
                continue
            # Sum debit amounts from posted journal items for this analytic account
            self.env.cr.execute("""
                SELECT COALESCE(SUM(aml.debit), 0)
                FROM account_move_line aml
                JOIN account_move am ON am.id = aml.move_id
                WHERE aml.analytic_distribution ? %s
                  AND am.state = 'posted'
            """, (str(rec.id),))
            consumed = self.env.cr.fetchone()[0]
            rec.budget_consumed = consumed
            rec.budget_remaining = rec.budget_allocated - consumed
