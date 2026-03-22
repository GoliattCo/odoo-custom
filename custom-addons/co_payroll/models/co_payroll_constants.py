from odoo import api, fields, models

# Default constants for 2024
DEFAULT_SMLMV = 1300000
DEFAULT_UVT = 47065
DEFAULT_TRANSPORT_ALLOWANCE = 162000


class CoPayrollConstants(models.Model):
    """Stores configurable payroll constants per year."""
    _name = 'co.payroll.constants'
    _description = 'Colombian Payroll Constants'
    _order = 'year desc'
    _rec_name = 'year'

    year = fields.Integer(
        string='Year', required=True, default=lambda self: fields.Date.today().year,
    )
    smlmv = fields.Float(
        string='SMLMV', required=True, default=DEFAULT_SMLMV,
        help='Salario Mínimo Legal Mensual Vigente',
    )
    uvt = fields.Float(
        string='UVT', required=True, default=DEFAULT_UVT,
        help='Unidad de Valor Tributario',
    )
    transport_allowance = fields.Float(
        string='Transport Allowance', required=True, default=DEFAULT_TRANSPORT_ALLOWANCE,
        help='Auxilio de Transporte',
    )

    _sql_constraints = [
        ('year_unique', 'UNIQUE(year)', 'Only one constants record per year is allowed.'),
    ]

    @api.model
    def get_current(self):
        """Return the constants record for the current year, or the most recent one."""
        current_year = fields.Date.today().year
        rec = self.search([('year', '=', current_year)], limit=1)
        if not rec:
            rec = self.search([], limit=1)
        return rec
