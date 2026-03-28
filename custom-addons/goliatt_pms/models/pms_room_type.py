from odoo import api, fields, models, _


class PmsRoomType(models.Model):
    _name = 'pms.room.type'
    _description = 'Room Type'
    _order = 'sequence, name'

    name = fields.Char(required=True)
    code = fields.Char(
        string='Code',
        help='Short code, e.g. STD, DLX, STE',
    )
    property_id = fields.Many2one(
        'pms.property',
        required=True,
        string='Property',
        ondelete='cascade',
    )
    product_id = fields.Many2one(
        'product.product',
        string='Service Product',
        help='Auto-created service product for billing.',
    )
    max_adults = fields.Integer(default=2, string='Max Adults')
    max_children = fields.Integer(default=1, string='Max Children')
    max_occupancy = fields.Integer(
        compute='_compute_max_occupancy',
        string='Max Occupancy',
        store=True,
    )
    bed_type = fields.Selection(
        [
            ('king', 'King'),
            ('queen', 'Queen'),
            ('twin', 'Twin'),
            ('double', 'Double'),
            ('single', 'Single'),
            ('sofa_bed', 'Sofa Bed'),
            ('bunk', 'Bunk'),
        ],
        string='Bed Type',
    )
    room_size_sqm = fields.Float(string='Room Size (sqm)')
    view_type = fields.Selection(
        [
            ('ocean', 'Ocean'),
            ('garden', 'Garden'),
            ('city', 'City'),
            ('pool', 'Pool'),
            ('mountain', 'Mountain'),
            ('none', 'None'),
        ],
        string='View Type',
        default='none',
    )
    base_rate = fields.Float(
        string='Base Rate',
        help='Rack rate per night.',
    )
    amenity_ids = fields.Many2many(
        'pms.amenity',
        'pms_room_type_amenity_rel',
        'room_type_id',
        'amenity_id',
        string='Amenities',
    )
    description = fields.Html(string='Description')
    image = fields.Binary(string='Image', attachment=True)
    room_ids = fields.One2many(
        'pms.room',
        'room_type_id',
        string='Rooms',
    )
    room_count = fields.Integer(
        compute='_compute_room_count',
        string='Room Count',
        store=True,
    )
    sequence = fields.Integer(default=10)

    @api.depends('max_adults', 'max_children')
    def _compute_max_occupancy(self):
        for rec in self:
            rec.max_occupancy = rec.max_adults + rec.max_children

    @api.depends('room_ids')
    def _compute_room_count(self):
        for rec in self:
            rec.room_count = len(rec.room_ids)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            if not rec.product_id:
                product = self.env['product.product'].create({
                    'name': f'{rec.property_id.name} - {rec.name}',
                    'type': 'service',
                    'list_price': rec.base_rate,
                    'sale_ok': True,
                    'purchase_ok': False,
                })
                rec.product_id = product.id
        return records
