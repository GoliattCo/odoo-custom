{
    'name': 'Colombian Bank Reconciliation',
    'version': '19.0.1.0.0',
    'summary': 'Bank reconciliation via flat file import from Colombian banks',
    'description': """
Colombian Bank Reconciliation
==============================
Import bank statement flat files (CSV/TXT) from major Colombian banks
and reconcile them against journal entries, payments, and invoices.

Supported banks:
- Bancolombia
- Davivienda
- Generic CSV/TXT (configurable column mapping)

Features:
- Auto-detection of partners from payment/invoice references
- Configurable matching rules (reference, amount, date tolerance)
- Manual reconciliation UI for unmatched lines
- Support for Colombian number formats and encodings
    """,
    'category': 'Accounting',
    'author': 'Custom',
    'license': 'LGPL-3',
    'depends': ['account'],
    'data': [
        'security/ir.model.access.csv',
        'data/co_bank_format_data.xml',
        'views/co_bank_format_views.xml',
        'views/co_bank_statement_import_views.xml',
        'views/co_bank_statement_line_views.xml',
        'wizard/co_bank_import_wizard_views.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'auto_install': False,
}
