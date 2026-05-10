{
    'name': 'Aged Payable Report',
    'version': '19.0.1.0.0',
    'summary': 'Aged payable report with aging buckets and PDF export',
    'category': 'Accounting',
    'depends': ['account', 'co_accounting_extended'],
    'data': [
        'security/ir.model.access.csv',
        'views/account_aged_payable_views.xml',
        'report/account_aged_payable_template.xml',
    ],
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
