from odoo import fields, models


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    business_unit_id = fields.Many2one(
        'co.business.unit',
        string='Business Unit',
        index=True,
        help='Business unit associated with this journal item.',
    )
    cost_center_notes = fields.Char(
        string='Cost Center Notes',
        help='Additional notes related to cost center allocation.',
    )
