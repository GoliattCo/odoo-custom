from odoo import api, fields, models, _


class StockWarehouseOrderpoint(models.Model):
    _inherit = 'stock.warehouse.orderpoint'

    supplier_lead_time = fields.Float(
        string='Supplier Lead Time (days)',
        help='Average number of days the supplier takes to deliver this product.',
    )
    safety_stock_days = fields.Float(
        string='Safety Stock Days',
        help='Number of days of safety stock to maintain above the minimum.',
    )
    safety_stock_qty = fields.Float(
        string='Safety Stock Qty',
        compute='_compute_safety_stock_qty',
        store=True,
        help='Computed safety stock quantity based on average daily consumption and safety days.',
    )
    avg_daily_consumption = fields.Float(
        string='Avg Daily Consumption',
        help='Average daily consumption of this product. Used for safety stock calculation.',
    )
    auto_purchase_request = fields.Boolean(
        string='Auto Purchase Request',
        default=False,
        help='When checked, generate a purchase request instead of an RFQ when below reorder point.',
    )

    @api.depends('safety_stock_days', 'avg_daily_consumption')
    def _compute_safety_stock_qty(self):
        for rec in self:
            rec.safety_stock_qty = rec.safety_stock_days * rec.avg_daily_consumption

    def _procure_orderpoint_confirm(self, use_new_cursor=False, company_id=False, raise_user_error=True):
        """Override to create purchase requests for orderpoints with auto_purchase_request flag."""
        # Separate orderpoints that want purchase requests
        pr_orderpoints = self.filtered(lambda o: o.auto_purchase_request)
        normal_orderpoints = self - pr_orderpoints

        # Process normal orderpoints with standard logic
        if normal_orderpoints:
            super(StockWarehouseOrderpoint, normal_orderpoints)._procure_orderpoint_confirm(
                use_new_cursor=use_new_cursor,
                company_id=company_id,
                raise_user_error=raise_user_error,
            )

        # Create purchase requests for flagged orderpoints
        if pr_orderpoints:
            pr_orderpoints._create_purchase_requests()

    def _create_purchase_requests(self):
        """Create purchase requests for orderpoints that need replenishment."""
        PurchaseRequest = self.env['co.purchase.request']
        PurchaseRequestLine = self.env['co.purchase.request.line']

        for orderpoint in self:
            qty_to_order = orderpoint.qty_to_order
            if qty_to_order <= 0:
                continue

            # Find preferred supplier
            supplier = False
            if orderpoint.product_id.seller_ids:
                supplier = orderpoint.product_id.seller_ids[0].partner_id

            # Create request
            request = PurchaseRequest.create({
                'date_request': fields.Date.context_today(self),
                'user_id': self.env.user.id,
                'company_id': orderpoint.company_id.id,
                'reason': _('Auto-generated from reorder point: %s') % orderpoint.name,
            })
            PurchaseRequestLine.create({
                'request_id': request.id,
                'product_id': orderpoint.product_id.id,
                'quantity': qty_to_order,
                'supplier_id': supplier.id if supplier else False,
                'estimated_price': orderpoint.product_id.standard_price,
                'reason': _(
                    'Below reorder point. Current: %(qty).2f, Min: %(min).2f, Max: %(max).2f'
                ) % {
                    'qty': orderpoint.qty_on_hand,
                    'min': orderpoint.product_min_qty,
                    'max': orderpoint.product_max_qty,
                },
            })
