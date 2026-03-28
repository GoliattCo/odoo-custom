from odoo import api, fields, models, _


class PmsGuest(models.Model):
    _inherit = 'res.partner'

    is_hotel_guest = fields.Boolean(default=False, string='Is Hotel Guest')
    guest_id_type = fields.Selection(
        [
            ('passport', 'Passport'),
            ('national_id', 'National ID / Cedula'),
            ('driver_license', 'Driver License'),
            ('other', 'Other'),
        ],
        string='ID Document Type',
    )
    guest_id_number = fields.Char(string='ID Document Number')
    guest_id_expiry = fields.Date(string='ID Expiry')
    nationality_id = fields.Many2one(
        'res.country',
        string='Nationality',
    )
    date_of_birth = fields.Date(string='Date of Birth')
    gender = fields.Selection(
        [
            ('male', 'Male'),
            ('female', 'Female'),
            ('other', 'Other'),
        ],
        string='Gender',
    )
    vip_level = fields.Selection(
        [
            ('none', 'None'),
            ('silver', 'Silver'),
            ('gold', 'Gold'),
            ('platinum', 'Platinum'),
            ('diamond', 'Diamond'),
        ],
        default='none',
        string='VIP Level',
    )
    total_stays = fields.Integer(
        compute='_compute_stay_stats',
        string='Total Stays',
    )
    total_nights = fields.Integer(
        compute='_compute_stay_stats',
        string='Total Nights',
    )
    total_revenue = fields.Float(
        compute='_compute_stay_stats',
        string='Total Revenue',
    )
    last_stay_date = fields.Date(
        compute='_compute_stay_stats',
        string='Last Stay',
    )
    preference_notes = fields.Text(string='Guest Preferences')
    reservation_ids = fields.One2many(
        'pms.reservation',
        'guest_id',
        string='Reservations',
    )

    def _compute_stay_stats(self):
        for partner in self:
            completed = partner.reservation_ids.filtered(
                lambda r: r.state == 'checked_out'
            )
            partner.total_stays = len(completed)
            partner.total_nights = sum(completed.mapped('nights'))
            partner.total_revenue = sum(completed.mapped('total_amount'))
            dates = completed.mapped('checkout_date')
            partner.last_stay_date = max(dates) if dates else False
