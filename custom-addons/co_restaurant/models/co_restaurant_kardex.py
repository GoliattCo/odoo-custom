from odoo import api, fields, models, tools


class CoRestaurantKardex(models.Model):
    _name = 'co.restaurant.kardex'
    _description = 'Inventory Kardex'
    _auto = False
    _order = 'date desc, id desc'

    product_id = fields.Many2one('product.product', string='Product', readonly=True)
    product_categ_id = fields.Many2one('product.category', string='Product Category', readonly=True)
    date = fields.Datetime(string='Date', readonly=True)
    reference = fields.Char(string='Reference', readonly=True)
    origin = fields.Char(string='Origin', readonly=True)
    move_type = fields.Selection([
        ('in', 'Entry'),
        ('out', 'Exit'),
        ('internal', 'Internal'),
    ], string='Type', readonly=True)
    location_id = fields.Many2one('stock.location', string='Source Location', readonly=True)
    location_dest_id = fields.Many2one('stock.location', string='Destination Location', readonly=True)
    warehouse_id = fields.Many2one('stock.warehouse', string='Warehouse', readonly=True)
    qty_in = fields.Float(string='Qty In', readonly=True, digits='Product Unit of Measure')
    qty_out = fields.Float(string='Qty Out', readonly=True, digits='Product Unit of Measure')
    balance = fields.Float(string='Balance', readonly=True, digits='Product Unit of Measure')
    uom_id = fields.Many2one('uom.uom', string='UoM', readonly=True)
    unit_cost = fields.Float(string='Unit Cost', readonly=True, digits='Product Price')
    total_cost_in = fields.Float(string='Cost In', readonly=True, digits='Product Price')
    total_cost_out = fields.Float(string='Cost Out', readonly=True, digits='Product Price')
    company_id = fields.Many2one('res.company', string='Company', readonly=True)
    picking_id = fields.Many2one('stock.picking', string='Picking', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                WITH moves AS (
                    SELECT
                        sm.id,
                        sm.product_id,
                        pt.categ_id AS product_categ_id,
                        sm.date,
                        sm.reference,
                        sm.origin,
                        sm.location_id,
                        sm.location_dest_id,
                        sm.picking_id,
                        sm.product_uom_qty,
                        sm.product_uom,
                        sm.price_unit,
                        sm.company_id,
                        -- Determine warehouse from internal locations
                        COALESCE(
                            wh_dest.id,
                            wh_src.id
                        ) AS warehouse_id,
                        CASE
                            WHEN sl_src.usage != 'internal'
                                 AND sl_dest.usage = 'internal'
                            THEN 'in'
                            WHEN sl_src.usage = 'internal'
                                 AND sl_dest.usage != 'internal'
                            THEN 'out'
                            ELSE 'internal'
                        END AS move_type,
                        CASE
                            WHEN sl_src.usage != 'internal'
                                 AND sl_dest.usage = 'internal'
                            THEN sm.product_uom_qty
                            ELSE 0
                        END AS qty_in,
                        CASE
                            WHEN sl_src.usage = 'internal'
                                 AND sl_dest.usage != 'internal'
                            THEN sm.product_uom_qty
                            ELSE 0
                        END AS qty_out
                    FROM stock_move sm
                    JOIN stock_location sl_src ON sl_src.id = sm.location_id
                    JOIN stock_location sl_dest ON sl_dest.id = sm.location_dest_id
                    JOIN product_product pp ON pp.id = sm.product_id
                    JOIN product_template pt ON pt.id = pp.product_tmpl_id
                    LEFT JOIN stock_warehouse wh_dest
                        ON sl_dest.warehouse_id = wh_dest.id
                    LEFT JOIN stock_warehouse wh_src
                        ON sl_src.warehouse_id = wh_src.id
                    WHERE sm.state = 'done'
                      AND (sl_src.usage = 'internal' OR sl_dest.usage = 'internal')
                )
                SELECT
                    m.id,
                    m.product_id,
                    m.product_categ_id,
                    m.date,
                    m.reference,
                    m.origin,
                    m.move_type,
                    m.location_id,
                    m.location_dest_id,
                    m.warehouse_id,
                    m.qty_in,
                    m.qty_out,
                    SUM(m.qty_in - m.qty_out) OVER (
                        PARTITION BY m.product_id
                        ORDER BY m.date, m.id
                    ) AS balance,
                    m.product_uom AS uom_id,
                    m.price_unit AS unit_cost,
                    m.qty_in * m.price_unit AS total_cost_in,
                    m.qty_out * m.price_unit AS total_cost_out,
                    m.company_id,
                    m.picking_id
                FROM moves m
            )
        """ % self._table)
