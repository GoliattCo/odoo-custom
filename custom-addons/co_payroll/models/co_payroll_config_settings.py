from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    co_payroll_smlmv = fields.Float(
        string='SMLMV',
        help='Salario Mínimo Legal Mensual Vigente',
    )
    co_payroll_uvt = fields.Float(
        string='UVT',
        help='Unidad de Valor Tributario',
    )
    co_payroll_transport_allowance = fields.Float(
        string='Transport Allowance',
        help='Auxilio de Transporte',
    )
    co_payroll_year = fields.Integer(
        string='Constants Year',
    )

    def set_values(self):
        super().set_values()
        Constants = self.env['co.payroll.constants']
        year = self.co_payroll_year or fields.Date.today().year
        rec = Constants.search([('year', '=', year)], limit=1)
        vals = {
            'year': year,
            'smlmv': self.co_payroll_smlmv,
            'uvt': self.co_payroll_uvt,
            'transport_allowance': self.co_payroll_transport_allowance,
        }
        if rec:
            rec.write(vals)
        else:
            Constants.create(vals)

    @api.model
    def get_values(self):
        res = super().get_values()
        constants = self.env['co.payroll.constants'].get_current()
        if constants:
            res.update({
                'co_payroll_smlmv': constants.smlmv,
                'co_payroll_uvt': constants.uvt,
                'co_payroll_transport_allowance': constants.transport_allowance,
                'co_payroll_year': constants.year,
            })
        return res
