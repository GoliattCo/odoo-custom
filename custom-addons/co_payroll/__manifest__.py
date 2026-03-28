{
    'name': 'Colombian Payroll (Nómina Colombiana)',
    'version': '19.0.1.0.0',
    'summary': 'Colombian payroll management compliant with Colombian labor law',
    'description': """
        Colombian Payroll Management
        ============================
        - Hiring process with approval workflow
        - Employee contracts (indefinido, fijo, obra/labor, aprendizaje)
        - Payslip generation (monthly/biweekly)
        - Social security (EPS, AFP, ARL, Caja, ICBF, SENA)
        - PILA generation
        - Contract termination (liquidación)
        - Overtime and surcharges (HED, HEN, HEDDF, HENDF)
        - Loans and manual deductions
        - Employee family group / dependents
        - Formulated salary concepts
        - Nomina Electrónica placeholder
        - Configurable constants (SMLMV, UVT, Transport Allowance)
    """,
    'category': 'Human Resources/Payroll',
    'author': 'Custom Development',
    'license': 'LGPL-3',
    'depends': [
        'hr',
        'hr_contract_community',
        'hr_attendance',
        'account',
        'mail',
    ],
    'data': [
        # Security
        'security/co_payroll_groups.xml',
        'security/ir.model.access.csv',
        # Data
        'data/co_payroll_constants.xml',
        'data/co_payroll_eps_data.xml',
        'data/co_payroll_afp_data.xml',
        'data/co_payroll_arl_data.xml',
        'data/co_payroll_concepts_data.xml',
        'data/co_payroll_uvt_table.xml',
        # Views (action-defining files first, menus last)
        'views/co_payroll_config_settings_views.xml',
        'views/co_hiring_request_views.xml',
        'views/co_hr_contract_views.xml',
        'views/co_payslip_views.xml',
        'views/co_payslip_line_views.xml',
        'views/co_social_security_views.xml',
        'views/co_pila_views.xml',
        'views/co_eps_entity_views.xml',
        'views/co_afp_entity_views.xml',
        'views/co_arl_entity_views.xml',
        'views/co_overtime_views.xml',
        'views/co_deduction_views.xml',
        'views/co_loan_views.xml',
        'views/co_family_member_views.xml',
        'views/co_salary_concept_views.xml',
        'views/co_nomina_electronica_views.xml',
        'views/co_payroll_menus.xml',
        # Wizard
        'wizard/co_contract_termination_wizard_views.xml',
        # Reports
        'report/co_payslip_report_template.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': True,
}
