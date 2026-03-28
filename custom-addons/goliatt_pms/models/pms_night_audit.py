from odoo import api, fields, models, _
from odoo.exceptions import UserError


class PmsNightAudit(models.Model):
    _name = 'pms.night.audit'
    _description = 'Night Audit'
    _inherit = ['mail.thread']
    _order = 'audit_date desc'

    name = fields.Char(
        string='Audit No.',
        readonly=True,
        copy=False,
        index=True,
        default=lambda self: _('New'),
    )
    property_id = fields.Many2one(
        'pms.property',
        required=True,
        string='Property',
    )
    audit_date = fields.Date(
        required=True,
        string='Audit Date',
    )
    auditor_id = fields.Many2one(
        'res.users',
        string='Auditor',
        default=lambda self: self.env.user,
    )
    state = fields.Selection(
        [
            ('pending', 'Pending'),
            ('in_progress', 'In Progress'),
            ('completed', 'Completed'),
        ],
        default='pending',
        string='State',
        tracking=True,
    )
    rooms_sold = fields.Integer(
        compute='_compute_stats',
        string='Rooms Sold',
        store=True,
    )
    occupancy_pct = fields.Float(
        compute='_compute_stats',
        string='Occupancy %',
        store=True,
    )
    total_revenue = fields.Float(
        compute='_compute_stats',
        string='Total Revenue',
        store=True,
    )
    adr = fields.Float(
        compute='_compute_stats',
        string='ADR',
        store=True,
        help='Average Daily Rate',
    )
    revpar = fields.Float(
        compute='_compute_stats',
        string='RevPAR',
        store=True,
        help='Revenue Per Available Room',
    )
    notes = fields.Text(string='Notes')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'pms.night.audit'
                ) or _('New')
        return super().create(vals_list)

    @api.depends('property_id', 'audit_date', 'state')
    def _compute_stats(self):
        Reservation = self.env['pms.reservation']
        for audit in self:
            if not audit.property_id or not audit.audit_date:
                audit.rooms_sold = 0
                audit.occupancy_pct = 0.0
                audit.total_revenue = 0.0
                audit.adr = 0.0
                audit.revpar = 0.0
                continue
            in_house = Reservation.search([
                ('property_id', '=', audit.property_id.id),
                ('checkin_date', '<=', audit.audit_date),
                ('checkout_date', '>', audit.audit_date),
                ('state', '=', 'checked_in'),
            ])
            audit.rooms_sold = len(in_house)
            total_rooms = audit.property_id.total_rooms or 1
            audit.occupancy_pct = (audit.rooms_sold / total_rooms) * 100
            audit.total_revenue = sum(in_house.mapped('daily_rate'))
            audit.adr = (
                audit.total_revenue / audit.rooms_sold
                if audit.rooms_sold
                else 0.0
            )
            audit.revpar = audit.total_revenue / total_rooms

    def action_run(self):
        """Run the night audit: post room charges, process no-shows, compute stats."""
        for audit in self:
            if audit.state == 'completed':
                raise UserError(_('This audit has already been completed.'))
            audit.state = 'in_progress'

            # Post room charges for in-house reservations
            in_house = self.env['pms.reservation'].search([
                ('property_id', '=', audit.property_id.id),
                ('checkin_date', '<=', audit.audit_date),
                ('checkout_date', '>', audit.audit_date),
                ('state', '=', 'checked_in'),
            ])
            for res in in_house:
                folio = res.folio_ids.filtered(
                    lambda f: f.state == 'open'
                )[:1]
                if not folio:
                    folio = self.env['pms.folio'].create({
                        'reservation_id': res.id,
                    })
                self.env['pms.folio.charge'].create({
                    'folio_id': folio.id,
                    'date': audit.audit_date,
                    'description': _('Room charge - %s', res.room_id.name or res.room_type_id.name),
                    'product_id': res.room_type_id.product_id.id if res.room_type_id.product_id else False,
                    'quantity': 1,
                    'unit_price': res.daily_rate,
                    'department': 'rooms',
                })

            # Process no-shows
            no_shows = self.env['pms.reservation'].search([
                ('property_id', '=', audit.property_id.id),
                ('checkin_date', '=', audit.audit_date),
                ('state', 'in', ('confirmed', 'guaranteed')),
            ])
            for res in no_shows:
                res.state = 'no_show'

            audit.state = 'completed'
