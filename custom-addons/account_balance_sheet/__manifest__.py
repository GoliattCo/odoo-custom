{
    'name': 'Balance Sheet Report',
    'version': '19.0.1.0.0',
    'summary': 'Live balance sheet report with PDF and Excel export',
    'category': 'Accounting',
    'depends': ['account'],
    'data': [
        'security/ir.model.access.csv',
        'views/account_balance_sheet_views.xml',
        'report/account_balance_sheet_template.xml',
    ],
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
