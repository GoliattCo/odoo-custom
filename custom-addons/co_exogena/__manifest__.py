{
    'name': 'Exogena - Informacion Exogena DIAN',
    'version': '18.0.1.0.0',
    'summary': 'Generacion de archivos de Informacion Exogena para la DIAN (Formatos 1001-1012)',
    'description': """
        Modulo para la generacion de archivos de Informacion Exogena
        requeridos por la DIAN en Colombia.

        Formatos soportados:
        - 1001: Pagos y abonos en cuenta
        - 1003: Retenciones en la fuente
        - 1005: IVA descontable
        - 1006: IVA generado
        - 1007: Ingresos recibidos
        - 1008: Cuentas por cobrar
        - 1009: Cuentas por pagar
        - 1010: Socios y accionistas
        - 1012: Declaraciones tributarias
    """,
    'category': 'Accounting',
    'author': 'Custom',
    'website': '',
    'depends': ['account', 'l10n_co'],
    'data': [
        'security/co_exogena_security.xml',
        'security/ir.model.access.csv',
        'data/co_exogena_concept_data.xml',
        'views/co_exogena_report_views.xml',
        'views/co_exogena_format_views.xml',
        'views/co_exogena_line_views.xml',
        'views/co_exogena_menus.xml',
        'wizard/co_exogena_generate_wizard_views.xml',
        'report/co_exogena_report_template.xml',
    ],
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
