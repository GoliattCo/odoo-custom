from odoo import api, fields, models, tools


class CoRestaurantCostAnalysis(models.Model):
    _name = 'co.restaurant.cost.analysis'
    _description = 'Recipe Cost Analysis'
    _auto = False
    _order = 'recipe_id, date'

    recipe_id = fields.Many2one('co.restaurant.recipe', string='Recipe', readonly=True)
    recipe_category_id = fields.Many2one(
        'co.restaurant.recipe.category', string='Category', readonly=True
    )
    date = fields.Date(string='Date', readonly=True)
    production_count = fields.Integer(string='Productions', readonly=True)
    total_planned_portions = fields.Float(
        string='Planned Portions', readonly=True, digits='Product Unit of Measure'
    )
    total_actual_portions = fields.Float(
        string='Actual Portions', readonly=True, digits='Product Unit of Measure'
    )
    theoretical_cost = fields.Float(
        string='Theoretical Cost', readonly=True, digits='Product Price',
        help='Cost based on recipe standard costs and planned quantities.',
    )
    actual_cost = fields.Float(
        string='Actual Cost', readonly=True, digits='Product Price',
        help='Cost based on actual ingredient consumption.',
    )
    cost_variance = fields.Float(
        string='Cost Variance', readonly=True, digits='Product Price',
    )
    cost_variance_pct = fields.Float(
        string='Variance %', readonly=True, digits=(5, 2),
    )
    selling_price = fields.Float(
        string='Selling Price', readonly=True, digits='Product Price',
    )
    theoretical_food_cost_pct = fields.Float(
        string='Theoretical Food Cost %', readonly=True, digits=(5, 2),
    )
    actual_food_cost_pct = fields.Float(
        string='Actual Food Cost %', readonly=True, digits=(5, 2),
    )
    waste_cost = fields.Float(
        string='Waste Cost', readonly=True, digits='Product Price',
    )
    company_id = fields.Many2one('res.company', string='Company', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                WITH prod_data AS (
                    SELECT
                        p.recipe_id,
                        p.date::date AS date,
                        p.company_id,
                        COUNT(p.id) AS production_count,
                        SUM(p.quantity) AS total_planned_portions,
                        SUM(COALESCE(p.actual_quantity, p.quantity)) AS total_actual_portions,
                        SUM(p.total_cost) AS actual_cost
                    FROM co_restaurant_production p
                    WHERE p.state = 'done'
                    GROUP BY p.recipe_id, p.date::date, p.company_id
                ),
                waste_data AS (
                    SELECT
                        w.recipe_id,
                        w.date::date AS date,
                        w.company_id,
                        SUM(w.total_cost) AS waste_cost
                    FROM co_restaurant_waste w
                    WHERE w.state = 'confirmed'
                      AND w.recipe_id IS NOT NULL
                    GROUP BY w.recipe_id, w.date::date, w.company_id
                )
                SELECT
                    ROW_NUMBER() OVER () AS id,
                    pd.recipe_id,
                    r.category_id AS recipe_category_id,
                    pd.date,
                    pd.production_count,
                    pd.total_planned_portions,
                    pd.total_actual_portions,
                    -- Theoretical cost = recipe cost_per_portion * planned portions
                    r.cost_per_portion * pd.total_planned_portions AS theoretical_cost,
                    pd.actual_cost,
                    pd.actual_cost - (r.cost_per_portion * pd.total_planned_portions) AS cost_variance,
                    CASE
                        WHEN r.cost_per_portion * pd.total_planned_portions > 0
                        THEN (
                            (pd.actual_cost - r.cost_per_portion * pd.total_planned_portions)
                            / (r.cost_per_portion * pd.total_planned_portions) * 100.0
                        )
                        ELSE 0
                    END AS cost_variance_pct,
                    r.selling_price,
                    CASE
                        WHEN r.selling_price > 0 AND pd.total_planned_portions > 0
                        THEN r.cost_per_portion / r.selling_price * 100.0
                        ELSE 0
                    END AS theoretical_food_cost_pct,
                    CASE
                        WHEN r.selling_price > 0 AND pd.total_actual_portions > 0
                        THEN (pd.actual_cost / pd.total_actual_portions) / r.selling_price * 100.0
                        ELSE 0
                    END AS actual_food_cost_pct,
                    COALESCE(wd.waste_cost, 0) AS waste_cost,
                    pd.company_id
                FROM prod_data pd
                JOIN co_restaurant_recipe r ON r.id = pd.recipe_id
                LEFT JOIN waste_data wd
                    ON wd.recipe_id = pd.recipe_id
                   AND wd.date = pd.date
                   AND wd.company_id = pd.company_id
            )
        """ % self._table)
