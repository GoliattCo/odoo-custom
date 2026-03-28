from odoo import api, fields, models, _
from odoo.exceptions import UserError


class PmsFolio(models.Model):
    _name = 'pms.folio'
    _description = 'Folio'
    _inherit = ['mail.thread']
    _order = 'name desc'

    name = fields.Char(
        string='Folio No.',
        readonly=True,
        copy=False,
        index=True,
        default=lambda self: _('New'),
    )
    reservation_id = fields.Many2one(
        'pms.reservation',
        required=True,
        string='Reservation',
        ondelete='cascade',
    )
    guest_id = fields.Many2one(
        'res.partner',
        related='reservation_id.guest_id',
        string='Guest',
        store=True,
    )
    property_id = fields.Many2one(
        'pms.property',
        related='reservation_id.property_id',
        string='Property',
        store=True,
    )
    state = fields.Selection(
        [
            ('open', 'Open'),
            ('closed', 'Closed'),
            ('void', 'Void'),
        ],
        default='open',
        string='State',
        tracking=True,
    )
    charge_ids = fields.One2many(
        'pms.folio.charge',
        'folio_id',
        string='Charges',
    )
    payment_ids = fields.One2many(
        'pms.folio.payment',
        'folio_id',
        string='Payments',
    )
    total_charges = fields.Float(
        compute='_compute_totals',
        string='Total Charges',
        store=True,
    )
    total_payments = fields.Float(
        compute='_compute_totals',
        string='Total Payments',
        store=True,
    )
    balance = fields.Float(
        compute='_compute_totals',
        string='Balance',
        store=True,
    )
    invoice_id = fields.Many2one(
        'account.move',
        string='Invoice',
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'pms.folio'
                ) or _('New')
        return super().create(vals_list)

    @api.depends(
        'charge_ids',
        'charge_ids.amount',
        'payment_ids',
        'payment_ids.amount',
    )
    def _compute_totals(self):
        for folio in self:
            folio.total_charges = sum(folio.charge_ids.mapped('amount'))
            folio.total_payments = sum(folio.payment_ids.mapped('amount'))
            folio.balance = folio.total_charges - folio.total_payments

    def action_create_invoice(self):
        self.ensure_one()
        if self.invoice_id:
            raise UserError(_('An invoice already exists for this folio.'))
        move_vals = {
            'move_type': 'out_invoice',
            'partner_id': self.guest_id.id,
            'invoice_line_ids': [],
        }
        for charge in self.charge_ids:
            move_vals['invoice_line_ids'].append((0, 0, {
                'name': charge.description,
                'product_id': charge.product_id.id if charge.product_id else False,
                'quantity': charge.quantity,
                'price_unit': charge.unit_price,
            }))
        invoice = self.env['account.move'].create(move_vals)
        self.invoice_id = invoice.id
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': invoice.id,
            'view_mode': 'form',
        }

    def action_close(self):
        for folio in self:
            if folio.balance != 0:
                raise UserError(
                    _('Cannot close folio with outstanding balance of %s.', folio.balance)
                )
            folio.state = 'closed'


class PmsFolioCharge(models.Model):
    _name = 'pms.folio.charge'
    _description = 'Folio Charge'
    _order = 'date desc, id desc'

    folio_id = fields.Many2one(
        'pms.folio',
        required=True,
        string='Folio',
        ondelete='cascade',
    )
    date = fields.Date(
        default=fields.Date.context_today,
        string='Date',
    )
    description = fields.Char(required=True, string='Description')
    product_id = fields.Many2one(
        'product.product',
        string='Product',
    )
    quantity = fields.Float(default=1.0, string='Quantity')
    unit_price = fields.Float(string='Unit Price')
    amount = fields.Float(
        compute='_compute_amount',
        string='Amount',
        store=True,
    )
    department = fields.Selection(
        [
            ('rooms', 'Rooms'),
            ('food_beverage', 'Food & Beverage'),
            ('spa', 'Spa'),
            ('minibar', 'Minibar'),
            ('laundry', 'Laundry'),
            ('telephone', 'Telephone'),
            ('parking', 'Parking'),
            ('other', 'Other'),
        ],
        string='Department',
        default='rooms',
    )
    pos_order_id = fields.Many2one(
        'pos.order',
        string='POS Order',
    )
    notes = fields.Char(string='Notes')

    @api.depends('quantity', 'unit_price')
    def _compute_amount(self):
        for charge in self:
            charge.amount = charge.quantity * charge.unit_price


class PmsFolioPayment(models.Model):
    _name = 'pms.folio.payment'
    _description = 'Folio Payment'
    _order = 'date desc, id desc'

    folio_id = fields.Many2one(
        'pms.folio',
        required=True,
        string='Folio',
        ondelete='cascade',
    )
    date = fields.Date(
        default=fields.Date.context_today,
        string='Date',
    )
    amount = fields.Float(required=True, string='Amount')
    payment_method = fields.Selection(
        [
            ('cash', 'Cash'),
            ('credit_card', 'Credit Card'),
            ('debit_card', 'Debit Card'),
            ('bank_transfer', 'Bank Transfer'),
            ('online', 'Online'),
            ('other', 'Other'),
        ],
        string='Payment Method',
        default='cash',
    )
    reference = fields.Char(string='Reference')
    notes = fields.Char(string='Notes')
