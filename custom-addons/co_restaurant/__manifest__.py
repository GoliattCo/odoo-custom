{
    'name': 'Restaurant Management (Colombia)',
    'version': '18.0.1.0.0',
    'summary': 'Recipes, production, kardex, waste tracking and cost analysis for restaurants',
    'description': """
Restaurant Management Module
=============================
Provides:
- Recipe management (extending MRP BoM concepts)
- Manual and automatic production tracking
- Presentation unit equivalences
- Inventory kardex per product
- Inventory adjustment wizard with variance report
- Portion control and waste tracking
- Food cost analysis and variance reports
    """,
    'category': 'Manufacturing/Restaurant',
    'author': 'Custom',
    'website': '',
    'license': 'LGPL-3',
    'depends': [
        'mrp',
        'stock',
        'product',
        'uom',
    ],
    'data': [
        # Security
        'security/co_restaurant_groups.xml',
        'security/ir.model.access.csv',
        # Data
        'data/co_restaurant_data.xml',
        # Views
        'views/co_restaurant_menus.xml',
        'views/co_restaurant_recipe_views.xml',
        'views/co_restaurant_production_views.xml',
        'views/co_restaurant_presentation_equiv_views.xml',
        'views/co_restaurant_kardex_views.xml',
        'views/co_restaurant_waste_views.xml',
        'views/co_restaurant_cost_analysis_views.xml',
        # Wizard
        'wizard/co_restaurant_inventory_adjustment_views.xml',
        # Reports
        'report/co_restaurant_report_templates.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': True,
}
