{
    'name': 'Fixed Assets (Colombia)',
    'version': '19.0.1.0.0',
    'summary': 'Fixed asset management with depreciation, maintenance, and disposal for Colombian companies',
    'description': """
        Manage fixed assets with:
        - Asset registration and categorization
        - Automatic depreciation schedule (straight-line / declining balance)
        - Monthly depreciation journal entries
        - Maintenance tracking (preventive / corrective)
        - Asset disposal with reversal entries
        - Cron job for monthly auto-depreciation
    """,
    'author': 'Custom',
    'category': 'Accounting',
    'depends': ['account', 'mail'],
    'data': [
        'security/co_fixed_assets_security.xml',
        'security/ir.model.access.csv',
        'data/co_fixed_assets_sequence.xml',
        'data/co_fixed_assets_cron.xml',
        'views/co_fixed_asset_views.xml',
        'views/co_fixed_asset_category_views.xml',
        'views/co_fixed_asset_depreciation_views.xml',
        'views/co_fixed_asset_maintenance_views.xml',
        'views/co_fixed_assets_menus.xml',
        'report/co_fixed_asset_report_template.xml',
    ],
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
