from odoo import api, fields, models, _
from odoo.exceptions import UserError


class CoPurchaseRequest(models.Model):
    _name = 'co.purchase.request'
    _description = 'Purchase Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name desc'

    name = fields.Char(
        string='Request Number',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New'),
    )
    date_request = fields.Date(
        string='Request Date',
        default=fields.Date.context_today,
        required=True,
        tracking=True,
    )
    date_approved = fields.Date(
        string='Approval Date',
        readonly=True,
        tracking=True,
    )
    user_id = fields.Many2one(
        'res.users',
        string='Requested By',
        default=lambda self: self.env.user,
        required=True,
        tracking=True,
    )
    approver_id = fields.Many2one(
        'res.users',
        string='Approved By',
        readonly=True,
        tracking=True,
    )
    department_id = fields.Many2one(
        'hr.department',
        string='Department',
        tracking=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True,
    )
    line_ids = fields.One2many(
        'co.purchase.request.line',
        'request_id',
        string='Request Lines',
    )
    state = fields.Selection(
        [
            ('draft', 'Draft'),
            ('submitted', 'Submitted'),
            ('approved', 'Approved'),
            ('purchase', 'Purchase Order Created'),
            ('done', 'Done'),
            ('cancel', 'Cancelled'),
        ],
        string='Status',
        default='draft',
        required=True,
        tracking=True,
    )
    purchase_order_ids = fields.One2many(
        'purchase.order',
        'co_purchase_request_id',
        string='Purchase Orders',
    )
    purchase_order_count = fields.Integer(
        string='Purchase Order Count',
        compute='_compute_purchase_order_count',
    )
    notes = fields.Html(string='Notes')
    reason = fields.Text(string='Justification')
    priority = fields.Selection(
        [
            ('0', 'Normal'),
            ('1', 'Urgent'),
            ('2', 'Very Urgent'),
        ],
        string='Priority',
        default='0',
        tracking=True,
    )

    @api.depends('purchase_order_ids')
    def _compute_purchase_order_count(self):
        for rec in self:
            rec.purchase_order_count = len(rec.purchase_order_ids)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'co.purchase.request'
                ) or _('New')
        return super().create(vals_list)

    def action_submit(self):
        for rec in self:
            if not rec.line_ids:
                raise UserError(_('You cannot submit a request without lines.'))
            rec.write({'state': 'submitted'})

    def action_approve(self):
        for rec in self:
            rec.write({
                'state': 'approved',
                'approver_id': self.env.user.id,
                'date_approved': fields.Date.context_today(self),
            })

    def action_cancel(self):
        for rec in self:
            if rec.state == 'purchase':
                raise UserError(_(
                    'Cannot cancel a request that already has purchase orders. '
                    'Cancel the purchase orders first.'
                ))
            rec.write({'state': 'cancel'})

    def action_draft(self):
        for rec in self:
            rec.write({'state': 'draft'})

    def action_create_purchase_order(self):
        """Convert approved purchase request into one or more POs grouped by supplier."""
        self.ensure_one()
        if self.state != 'approved':
            raise UserError(_('Only approved requests can be converted to purchase orders.'))

        # Group lines by supplier
        supplier_lines = {}
        for line in self.line_ids:
            if not line.supplier_id:
                raise UserError(_(
                    'Line "%s" has no supplier. Please set a supplier on all lines '
                    'before creating a purchase order.'
                ) % line.product_id.display_name)
            supplier_lines.setdefault(line.supplier_id.id, []).append(line)

        created_orders = self.env['purchase.order']

        for supplier_id, lines in supplier_lines.items():
            po_vals = {
                'partner_id': supplier_id,
                'co_purchase_request_id': self.id,
                'origin': self.name,
                'company_id': self.company_id.id,
            }
            po = self.env['purchase.order'].create(po_vals)

            for line in lines:
                self.env['purchase.order.line'].create({
                    'order_id': po.id,
                    'product_id': line.product_id.id,
                    'product_qty': line.quantity,
                    'product_uom': line.product_uom_id.id,
                    'price_unit': line.estimated_price,
                    'name': line.product_id.display_name,
                })

            created_orders |= po

        self.write({'state': 'purchase'})

        if len(created_orders) == 1:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'purchase.order',
                'res_id': created_orders.id,
                'view_mode': 'form',
                'target': 'current',
            }
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'purchase.order',
            'domain': [('id', 'in', created_orders.ids)],
            'view_mode': 'list,form',
            'target': 'current',
        }

    def action_view_purchase_orders(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'purchase.order',
            'domain': [('co_purchase_request_id', '=', self.id)],
            'view_mode': 'list,form',
            'name': _('Purchase Orders'),
            'target': 'current',
        }

    def action_done(self):
        for rec in self:
            rec.write({'state': 'done'})
