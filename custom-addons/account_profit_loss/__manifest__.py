{
    'name': 'Profit & Loss Report',
    'version': '19.0.1.0.0',
    'summary': 'Live Profit & Loss report with PDF export',
    'category': 'Accounting',
    'depends': ['account', 'co_accounting_extended'],
    'data': [
        'security/ir.model.access.csv',
        'views/account_profit_loss_views.xml',
        'report/account_profit_loss_template.xml',
    ],
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
