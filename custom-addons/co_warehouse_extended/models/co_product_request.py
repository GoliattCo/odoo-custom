from odoo import api, fields, models, _
from odoo.exceptions import UserError


class CoProductRequest(models.Model):
    _name = 'co.product.request'
    _description = 'Product Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name desc'

    name = fields.Char(
        string='Reference', required=True, copy=False,
        readonly=True, default='New')
    requester_id = fields.Many2one(
        'res.users', string='Requested By', required=True,
        default=lambda self: self.env.user, tracking=True)
    department_id = fields.Many2one('hr.department', tracking=True)
    company_id = fields.Many2one(
        'res.company', required=True,
        default=lambda self: self.env.company)
    warehouse_id = fields.Many2one(
        'stock.warehouse', string='Source Warehouse', required=True,
        default=lambda self: self.env['stock.warehouse'].search(
            [('company_id', '=', self.env.company.id)], limit=1),
        tracking=True)
    date_request = fields.Date(
        string='Request Date', required=True,
        default=fields.Date.context_today, tracking=True)
    line_ids = fields.One2many(
        'co.product.request.line', 'request_id', string='Requested Products')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('stock_check', 'Stock Checked'),
        ('splitting', 'Awaiting Split Decision'),
        ('processed', 'Processed'),
        ('done', 'Done'),
        ('cancel', 'Cancelled'),
    ], default='draft', tracking=True, string='Status')
    picking_ids = fields.Many2many(
        'stock.picking', string='Internal Transfers',
        copy=False)
    purchase_request_id = fields.Many2one(
        'co.purchase.request', string='Purchase Request',
        readonly=True, copy=False)
    notes = fields.Text()
    picking_count = fields.Integer(compute='_compute_picking_count')
    has_purchase = fields.Boolean(compute='_compute_has_purchase')

    @api.depends('picking_ids')
    def _compute_picking_count(self):
        for rec in self:
            rec.picking_count = len(rec.picking_ids)

    @api.depends('purchase_request_id')
    def _compute_has_purchase(self):
        for rec in self:
            rec.has_purchase = bool(rec.purchase_request_id)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'co.product.request') or 'New'
        return super().create(vals_list)

    def _get_effective_split_mode(self):
        self.ensure_one()
        wh_mode = self.warehouse_id.purchase_split_mode
        if wh_mode and wh_mode != 'company_default':
            return wh_mode
        return self.company_id.purchase_split_mode or 'auto'

    def action_check_availability(self):
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_('Please add at least one product line.'))
        warehouse = self.warehouse_id
        location = warehouse.lot_stock_id
        for line in self.line_ids:
            qty = line.product_id.with_context(
                location=location.id,
                warehouse_id=warehouse.id,
            ).qty_available
            line.qty_available = qty
            if qty >= line.qty_requested:
                line.line_state = 'available'
                line.qty_to_transfer = line.qty_requested
                line.qty_to_purchase = 0.0
            elif qty > 0:
                line.line_state = 'partial'
                line.qty_to_transfer = qty
                line.qty_to_purchase = line.qty_requested - qty
            else:
                line.line_state = 'unavailable'
                line.qty_to_transfer = 0.0
                line.qty_to_purchase = line.qty_requested

        split_mode = self._get_effective_split_mode()
        if split_mode == 'auto':
            self.state = 'stock_check'
            self.action_process()
        else:
            has_partial = any(
                l.line_state in ('partial', 'unavailable') for l in self.line_ids)
            if has_partial:
                self.state = 'splitting'
            else:
                self.state = 'stock_check'
                self.action_process()

    def action_confirm_split(self):
        self.ensure_one()
        for line in self.line_ids:
            if line.qty_to_transfer + line.qty_to_purchase != line.qty_requested:
                raise UserError(_(
                    'Line "%s": Transfer qty + Purchase qty must equal Requested qty (%s).',
                    line.product_id.display_name, line.qty_requested))
            if line.qty_to_transfer > line.qty_available:
                raise UserError(_(
                    'Line "%s": Cannot transfer more than available stock (%s).',
                    line.product_id.display_name, line.qty_available))
        self.action_process()

    def action_process(self):
        self.ensure_one()
        transfer_lines = self.line_ids.filtered(lambda l: l.qty_to_transfer > 0)
        purchase_lines = self.line_ids.filtered(lambda l: l.qty_to_purchase > 0)

        if transfer_lines:
            self._create_internal_transfer(transfer_lines)
        if purchase_lines:
            self._create_purchase_request(purchase_lines)

        self.state = 'processed'

    def _create_internal_transfer(self, lines):
        warehouse = self.warehouse_id
        picking_type = self.env['stock.picking.type'].search([
            ('code', '=', 'internal'),
            ('warehouse_id', '=', warehouse.id),
        ], limit=1)
        if not picking_type:
            raise UserError(_(
                'No internal transfer operation type found for warehouse %s.',
                warehouse.name))
        picking_vals = {
            'picking_type_id': picking_type.id,
            'location_id': warehouse.lot_stock_id.id,
            'location_dest_id': picking_type.default_location_dest_id.id or warehouse.lot_stock_id.id,
            'origin': self.name,
            'scheduled_date': fields.Datetime.now(),
            'move_ids': [(0, 0, {
                'name': line.product_id.display_name,
                'product_id': line.product_id.id,
                'product_uom_qty': line.qty_to_transfer,
                'product_uom': line.uom_id.id,
                'location_id': warehouse.lot_stock_id.id,
                'location_dest_id': picking_type.default_location_dest_id.id or warehouse.lot_stock_id.id,
            }) for line in lines],
        }
        picking = self.env['stock.picking'].create(picking_vals)
        picking.action_confirm()
        self.picking_ids = [(4, picking.id)]

    def _create_purchase_request(self, lines):
        pr_vals = {
            'user_id': self.requester_id.id,
            'department_id': self.department_id.id,
            'company_id': self.company_id.id,
            'reason': _('Generated from product request %s', self.name),
            'line_ids': [(0, 0, {
                'product_id': line.product_id.id,
                'quantity': line.qty_to_purchase,
                'estimated_price': line.product_id.standard_price,
                'supplier_id': (
                    line.product_id.seller_ids[:1].partner_id.id
                    if line.product_id.seller_ids else False),
            }) for line in lines],
        }
        purchase_request = self.env['co.purchase.request'].create(pr_vals)
        self.purchase_request_id = purchase_request.id

    def action_done(self):
        self.write({'state': 'done'})

    def action_cancel(self):
        self.write({'state': 'cancel'})

    def action_draft(self):
        self.write({'state': 'draft'})
        for line in self.line_ids:
            line.write({
                'qty_available': 0,
                'qty_to_transfer': 0,
                'qty_to_purchase': 0,
                'line_state': 'pending',
            })

    def action_view_pickings(self):
        self.ensure_one()
        action = self.env['ir.actions.actions']._for_xml_id(
            'stock.action_picking_tree_all')
        action['domain'] = [('id', 'in', self.picking_ids.ids)]
        return action

    def action_view_purchase_request(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'co.purchase.request',
            'view_mode': 'form',
            'res_id': self.purchase_request_id.id,
        }
