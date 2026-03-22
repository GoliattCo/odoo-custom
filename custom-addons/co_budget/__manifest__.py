{
    'name': 'Budget Management (Colombia)',
    'version': '18.0.1.0.0',
    'summary': 'Budget management with planned vs actual tracking and alerts',
    'description': """
        Budget management module for Colombian companies.
        Community Edition replacement for account_budget (Enterprise).

        Features:
        - Budget with fiscal year periods (monthly/quarterly/yearly)
        - Budget lines with planned vs actual comparison
        - Budget positions (account groups)
        - Threshold alerts (80%, 100% overspend warnings)
        - PDF report: Budget vs Actual
        - Full Spanish (es / es_419) translations
    """,
    'author': 'Manuel Caro',
    'category': 'Accounting',
    'depends': ['account', 'analytic', 'mail'],
    'data': [
        'security/co_budget_security.xml',
        'security/ir.model.access.csv',
        'report/co_budget_report_template.xml',
        'views/co_budget_position_views.xml',
        'views/co_budget_views.xml',
        'views/co_budget_line_views.xml',
        'views/co_budget_menus.xml',
    ],
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
    'application': False,
}
