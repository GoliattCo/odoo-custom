from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ClubCorporateGroup(models.Model):
    _name = 'club.corporate.group'
    _description = 'Club Corporate Group'

    name = fields.Char(
        related='company_partner_id.name', string='Name', store=True, readonly=True
    )
    company_partner_id = fields.Many2one(
        'res.partner',
        required=True,
        string='Company',
        domain=[('is_company', '=', True)],
    )
    admin_id = fields.Many2one(
        'club.affiliate', string='Corporate Admin'
    )
    employee_ids = fields.One2many(
        'club.affiliate', 'corporate_group_id', string='Authorized Members'
    )
    max_employees = fields.Integer(
        string='Max Authorized Members', default=10
    )
    employee_count = fields.Integer(
        compute='_compute_employee_count', string='Current Members'
    )

    @api.depends('employee_ids')
    def _compute_employee_count(self):
        for group in self:
            group.employee_count = len(group.employee_ids)

    @api.constrains('employee_ids', 'max_employees')
    def _check_employee_limit(self):
        for group in self:
            if group.max_employees > 0 and len(group.employee_ids) > group.max_employees:
                raise ValidationError(
                    _('Corporate group "%s" has exceeded the maximum of %d authorized members.')
                    % (group.name, group.max_employees)
                )
