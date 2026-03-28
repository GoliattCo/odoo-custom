from odoo import fields, models


class PmsAmenity(models.Model):
    _name = 'pms.amenity'
    _description = 'Room Amenity'
    _order = 'category, name'

    name = fields.Char(required=True, string='Amenity')
    icon = fields.Char(
        string='Icon CSS Class',
        help='CSS class for displaying an icon, e.g. fa-wifi',
    )
    category = fields.Selection(
        [
            ('room', 'Room'),
            ('bathroom', 'Bathroom'),
            ('technology', 'Technology'),
            ('entertainment', 'Entertainment'),
            ('other', 'Other'),
        ],
        string='Category',
        default='room',
    )
