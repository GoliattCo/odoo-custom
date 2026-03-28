from odoo import api, fields, models


class PmsAvailability(models.Model):
    _name = 'pms.availability'
    _description = 'Daily Availability'
    _order = 'date, property_id, room_type_id'

    property_id = fields.Many2one(
        'pms.property',
        required=True,
        string='Property',
    )
    room_type_id = fields.Many2one(
        'pms.room.type',
        required=True,
        string='Room Type',
    )
    date = fields.Date(required=True, string='Date')
    total_inventory = fields.Integer(string='Total Inventory')
    sold = fields.Integer(string='Sold')
    out_of_order = fields.Integer(string='Out of Order')
    available = fields.Integer(
        compute='_compute_available',
        string='Available',
        store=True,
    )
    rate = fields.Float(string='Rate')
    min_stay = fields.Integer(string='Min Stay')
    stop_sell = fields.Boolean(string='Stop Sell', default=False)

    _sql_constraints = [
        (
            'unique_availability',
            'unique(property_id, room_type_id, date)',
            'Availability record must be unique per property, room type, and date.',
        ),
    ]

    @api.depends('total_inventory', 'sold', 'out_of_order')
    def _compute_available(self):
        for rec in self:
            rec.available = rec.total_inventory - rec.sold - rec.out_of_order
