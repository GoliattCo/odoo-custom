{
    'name': 'HR Contracts (Community)',
    'version': '19.0.1.0.0',
    'summary': 'Basic employee contracts for Odoo Community Edition',
    'description': 'Provides hr.contract model for Community Edition (Enterprise-only in 19.0). '
                   'Required by co_payroll and other Colombian payroll modules.',
    'category': 'Human Resources',
    'author': 'Manuel Caro',
    'license': 'LGPL-3',
    'depends': ['hr'],
    'data': [
        'security/ir.model.access.csv',
        'views/hr_contract_views.xml',
    ],
    'installable': True,
    'application': False,
}
