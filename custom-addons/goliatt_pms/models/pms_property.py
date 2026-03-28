from odoo import api, fields, models, _


class PmsProperty(models.Model):
    _name = 'pms.property'
    _description = 'Hotel / Property'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name'

    name = fields.Char(required=True, tracking=True)
    code = fields.Char(
        string='Short Code',
        help='Short unique code, e.g. HTL01',
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Address / Contact',
        help='Contact record representing the property address.',
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True,
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='company_id.currency_id',
        string='Currency',
        store=True,
    )
    property_type = fields.Selection(
        [
            ('hotel', 'Hotel'),
            ('resort', 'Resort'),
            ('hostel', 'Hostel'),
            ('apartment', 'Apartment'),
            ('boutique', 'Boutique'),
            ('villa', 'Villa'),
        ],
        string='Property Type',
        default='hotel',
    )
    star_rating = fields.Selection(
        [
            ('1', '1 Star'),
            ('2', '2 Stars'),
            ('3', '3 Stars'),
            ('4', '4 Stars'),
            ('5', '5 Stars'),
        ],
        string='Star Rating',
    )
    check_in_time = fields.Float(
        string='Check-in Time',
        default=15.0,
        help='Default check-in time (24h float, e.g. 15.0 = 3 PM)',
    )
    check_out_time = fields.Float(
        string='Check-out Time',
        default=11.0,
        help='Default check-out time (24h float, e.g. 11.0 = 11 AM)',
    )
    timezone = fields.Char(
        string='Timezone',
        default='UTC',
    )
    room_type_ids = fields.One2many(
        'pms.room.type',
        'property_id',
        string='Room Types',
    )
    room_ids = fields.One2many(
        'pms.room',
        'property_id',
        string='Rooms',
    )
    total_rooms = fields.Integer(
        compute='_compute_total_rooms',
        string='Total Rooms',
        store=True,
    )
    active = fields.Boolean(default=True)
    image = fields.Binary(string='Image', attachment=True)
    notes = fields.Html(string='Notes')

    _sql_constraints = [
        ('code_uniq', 'unique(code)', 'Property code must be unique.'),
    ]

    @api.depends('room_ids')
    def _compute_total_rooms(self):
        for prop in self:
            prop.total_rooms = len(prop.room_ids)
