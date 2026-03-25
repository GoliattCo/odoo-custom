from odoo import fields, models


class ClubGuestVisitParty(models.Model):
    _name = 'club.guest.visit.party'
    _description = 'Guest Visit Party Member'
    _order = 'id'

    visit_id = fields.Many2one(
        'club.guest.visit', string='Visit', required=True,
        ondelete='cascade',
    )
    name = fields.Char(string='Full Name', required=True)
    identification = fields.Char(string='ID Number')
    relationship = fields.Selection(
        [
            ('family', 'Family'),
            ('friend', 'Friend'),
            ('colleague', 'Colleague'),
            ('child', 'Child'),
            ('other', 'Other'),
        ],
        string='Relationship to Guest',
    )
    age_group = fields.Selection(
        [
            ('adult', 'Adult'),
            ('minor', 'Minor'),
        ],
        string='Age Group',
        default='adult',
    )
    notes = fields.Char(string='Notes')
