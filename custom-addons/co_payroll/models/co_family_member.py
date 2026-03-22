from odoo import api, fields, models


class CoFamilyMember(models.Model):
    _name = 'co.family.member'
    _description = 'Employee Family Member / Dependent'
    _order = 'employee_id, name'

    employee_id = fields.Many2one(
        'hr.employee', string='Employee', required=True, ondelete='cascade',
    )
    name = fields.Char(string='Full Name', required=True)
    identification_type = fields.Selection([
        ('cc', 'Cédula de Ciudadanía'),
        ('ti', 'Tarjeta de Identidad'),
        ('rc', 'Registro Civil'),
        ('ce', 'Cédula de Extranjería'),
        ('passport', 'Pasaporte'),
    ], string='ID Type')
    identification_number = fields.Char(string='ID Number')
    relationship = fields.Selection([
        ('spouse', 'Spouse / Partner'),
        ('child', 'Child'),
        ('parent', 'Parent'),
        ('sibling', 'Sibling'),
        ('other', 'Other'),
    ], string='Relationship', required=True)
    birth_date = fields.Date(string='Birth Date')
    gender = fields.Selection([
        ('male', 'Male'),
        ('female', 'Female'),
        ('other', 'Other'),
    ], string='Gender')
    eps_id = fields.Many2one('co.eps.entity', string='EPS')
    eps_affiliated = fields.Boolean(string='EPS Affiliated', default=False)
    is_dependent_for_tax = fields.Boolean(
        string='Dependent for Tax',
        help='Mark if this person qualifies as a dependent for withholding tax deductions',
    )
    active = fields.Boolean(default=True)
    notes = fields.Text(string='Notes')

    @api.depends('name', 'relationship')
    def _compute_display_name(self):
        for rec in self:
            rel_label = dict(
                rec._fields['relationship'].selection
            ).get(rec.relationship, '')
            rec.display_name = f"{rec.name} ({rel_label})" if rel_label else rec.name
