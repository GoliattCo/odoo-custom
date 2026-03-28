from odoo import api, fields, models, _


class PmsRoom(models.Model):
    _name = 'pms.room'
    _description = 'Room'
    _inherit = ['mail.thread']
    _order = 'name'

    name = fields.Char(
        required=True,
        string='Room Number',
        help='Room number, e.g. 101, 201A',
    )
    room_type_id = fields.Many2one(
        'pms.room.type',
        required=True,
        string='Room Type',
        ondelete='restrict',
    )
    property_id = fields.Many2one(
        'pms.property',
        related='room_type_id.property_id',
        string='Property',
        store=True,
    )
    floor = fields.Char(string='Floor', help='e.g. 1, 2, PH')
    building = fields.Char(string='Building')
    status = fields.Selection(
        [
            ('available', 'Available'),
            ('occupied', 'Occupied'),
            ('out_of_order', 'Out of Order'),
            ('out_of_service', 'Out of Service'),
        ],
        default='available',
        string='Status',
        tracking=True,
    )
    housekeeping_status = fields.Selection(
        [
            ('clean', 'Clean'),
            ('dirty', 'Dirty'),
            ('cleaning', 'Cleaning'),
            ('inspected', 'Inspected'),
            ('pickup', 'Pick-up'),
        ],
        default='clean',
        string='Housekeeping',
        tracking=True,
    )
    is_smoking = fields.Boolean(string='Smoking Room')
    is_accessible = fields.Boolean(string='Accessible Room')
    connecting_room_id = fields.Many2one(
        'pms.room',
        string='Connecting Room',
    )
    current_reservation_id = fields.Many2one(
        'pms.reservation',
        string='Current Reservation',
    )
    current_guest_name = fields.Char(
        compute='_compute_current_guest_name',
        string='Current Guest',
    )
    notes = fields.Text(string='Notes')
    active = fields.Boolean(default=True)

    _sql_constraints = [
        (
            'name_property_uniq',
            'unique(name, property_id)',
            'Room number must be unique per property.',
        ),
    ]

    @api.depends('current_reservation_id', 'current_reservation_id.guest_id')
    def _compute_current_guest_name(self):
        for room in self:
            if room.current_reservation_id and room.current_reservation_id.guest_id:
                room.current_guest_name = room.current_reservation_id.guest_id.name
            else:
                room.current_guest_name = False
