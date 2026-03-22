from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class CoFixedAssetMaintenance(models.Model):
    _name = 'co.fixed.asset.maintenance'
    _description = 'Fixed Asset Maintenance'
    _order = 'date desc, id desc'
    _inherit = ['mail.thread']

    asset_id = fields.Many2one(
        'co.fixed.asset',
        string='Asset',
        required=True,
        ondelete='cascade',
        index=True,
    )
    name = fields.Char(
        string='Description',
        required=True,
    )
    maintenance_type = fields.Selection(
        [
            ('preventive', 'Preventive'),
            ('corrective', 'Corrective'),
        ],
        string='Type',
        required=True,
        default='preventive',
        tracking=True,
    )
    date = fields.Date(
        string='Date',
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )
    next_date = fields.Date(
        string='Next Maintenance Date',
        tracking=True,
    )
    cost = fields.Monetary(
        string='Cost',
        currency_field='currency_id',
        tracking=True,
    )
    currency_id = fields.Many2one(
        related='asset_id.currency_id',
        store=True,
    )
    responsible_id = fields.Many2one(
        'res.users',
        string='Performed By',
        default=lambda self: self.env.user,
    )
    note = fields.Text(
        string='Notes',
    )

    @api.constrains('cost')
    def _check_cost(self):
        for rec in self:
            if rec.cost < 0:
                raise ValidationError(_('Maintenance cost cannot be negative.'))
