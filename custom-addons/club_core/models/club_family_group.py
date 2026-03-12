from odoo import fields, models


class ClubFamilyGroup(models.Model):
    _name = 'club.family.group'
    _description = 'Club Family Group'

    name = fields.Char(
        related='primary_member_id.name', string='Name', store=True, readonly=True
    )
    primary_member_id = fields.Many2one(
        'club.affiliate', required=True, string='Primary Member'
    )
    dependent_ids = fields.One2many(
        'club.affiliate', 'family_group_id', string='Dependents'
    )
    billing_affiliate_id = fields.Many2one(
        'club.affiliate',
        string='Billing Member',
        help='Who receives the invoices. Defaults to primary member if empty.',
    )

    def get_billing_affiliate(self):
        """Return billing affiliate or fall back to primary member."""
        self.ensure_one()
        return self.billing_affiliate_id or self.primary_member_id
