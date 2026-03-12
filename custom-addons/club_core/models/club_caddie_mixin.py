from odoo import fields, models


class ClubCaddieMixin(models.AbstractModel):
    """Abstract mixin shared by club.golf.caddie and club.tennis.caddie.
    Provides common partner link and employee number fields.
    Sport-specific availability models are defined in each sport module.
    """
    _name = 'club.caddie.mixin'
    _description = 'Club Caddie/Staff Mixin'

    partner_id = fields.Many2one(
        'res.partner', required=True, string='Person', ondelete='cascade'
    )
    employee_number = fields.Char(string='Employee Number')
