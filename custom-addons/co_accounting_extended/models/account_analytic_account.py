from odoo import api, fields, models


class AccountAnalyticAccount(models.Model):
    _inherit = 'account.analytic.account'

    is_cost_center = fields.Boolean(
        string='Es Centro de Costo',
        default=False,
        help='Marcar esta cuenta analítica como centro de costo.',
    )
    cost_center_parent_id = fields.Many2one(
        'account.analytic.account',
        string='Centro de Costo Padre',
        domain="[('is_cost_center', '=', True)]",
        help='Centro de costo padre jerárquico.',
    )
    cost_center_child_ids = fields.One2many(
        'account.analytic.account',
        'cost_center_parent_id',
        string='Centros de Costo Hijos',
    )
    responsible_id = fields.Many2one(
        'res.users',
        string='Responsable',
        help='Persona responsable de este centro de costo.',
    )
    budget_allocated = fields.Monetary(
        string='Presupuesto Asignado',
        currency_field='currency_id',
        help='Presupuesto anual asignado a este centro de costo.',
    )
    budget_consumed = fields.Monetary(
        string='Presupuesto Consumido',
        currency_field='currency_id',
        compute='_compute_budget_consumed',
        help='Monto total consumido del presupuesto asignado.',
    )
    budget_remaining = fields.Monetary(
        string='Presupuesto Restante',
        currency_field='currency_id',
        compute='_compute_budget_consumed',
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='company_id.currency_id',
        store=True,
    )
    cost_center_notes = fields.Text(string='Notas del Centro de Costo')

    @api.depends('budget_allocated')
    def _compute_budget_consumed(self):
        """Compute consumed budget from posted journal items linked to this analytic account."""
        for rec in self:
            if not rec.is_cost_center or not rec.id:
                rec.budget_consumed = 0.0
                rec.budget_remaining = rec.budget_allocated
                continue
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
