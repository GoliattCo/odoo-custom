from odoo import api, fields, models


class CoNominaElectronica(models.Model):
    """Placeholder model for DIAN Nómina Electrónica.

    This model stores the structure and fields needed for electronic payroll
    XML generation as required by DIAN. Full DIAN integration (signing,
    sending, validation) is not implemented - this is a structural placeholder.
    """
    _name = 'co.nomina.electronica'
    _description = 'Electronic Payroll (Nómina Electrónica)'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    name = fields.Char(
        string='Reference', required=True, copy=False, readonly=True,
        default='New',
    )
    payslip_id = fields.Many2one(
        'co.payslip', string='Payslip', required=True,
    )
    employee_id = fields.Many2one(
        related='payslip_id.employee_id', store=True,
    )
    company_id = fields.Many2one(
        related='payslip_id.company_id', store=True,
    )

    # DIAN document fields
    document_type = fields.Selection([
        ('102', 'Nómina Individual'),
        ('103', 'Nómina de Ajuste'),
    ], string='Document Type', default='102')
    predecessor_id = fields.Many2one(
        'co.nomina.electronica', string='Predecessor Document',
        help='For adjustment documents (type 103)',
    )
    generation_date = fields.Datetime(
        string='Generation Date', default=fields.Datetime.now,
    )
    period_start = fields.Date(related='payslip_id.date_from')
    period_end = fields.Date(related='payslip_id.date_to')

    # Employer info (from company)
    employer_nit = fields.Char(string='Employer NIT')
    employer_name = fields.Char(string='Employer Name')

    # Employee info
    employee_document_type = fields.Char(string='Employee Doc Type')
    employee_document_number = fields.Char(string='Employee Doc Number')

    # Payment info
    payment_method = fields.Selection([
        ('1', 'Cash'),
        ('2', 'Bank Transfer'),
        ('3', 'Check'),
    ], string='Payment Method', default='2')
    payment_date = fields.Date(string='Payment Date')

    # Totals (from payslip)
    total_earnings = fields.Float(related='payslip_id.total_earnings')
    total_deductions = fields.Float(related='payslip_id.total_deductions')
    net_pay = fields.Float(related='payslip_id.net_pay')

    # XML content (placeholder)
    xml_content = fields.Text(string='XML Content', readonly=True)
    xml_filename = fields.Char(string='XML Filename')

    # DIAN response (placeholder)
    cune = fields.Char(
        string='CUNE',
        help='Código Único de Nómina Electrónica',
    )
    dian_status = fields.Selection([
        ('pending', 'Pending'),
        ('sent', 'Sent'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
    ], string='DIAN Status', default='pending')
    dian_response = fields.Text(string='DIAN Response')

    state = fields.Selection([
        ('draft', 'Draft'),
        ('generated', 'XML Generated'),
        ('sent', 'Sent to DIAN'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', tracking=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'co.nomina.electronica'
                ) or 'New'
        return super().create(vals_list)

    def action_generate_xml(self):
        """Placeholder: Generate XML structure for DIAN submission."""
        for rec in self:
            # Populate employer/employee info
            company = rec.company_id
            employee = rec.employee_id
            rec.write({
                'employer_nit': company.vat or '',
                'employer_name': company.name or '',
                'employee_document_number': employee.identification_id or '',
                'xml_content': self._build_xml_placeholder(rec),
                'xml_filename': f'NE_{rec.name}.xml',
                'state': 'generated',
            })

    @api.model
    def _build_xml_placeholder(self, record):
        """Build a placeholder XML structure. Real implementation would
        follow DIAN technical annex for Nómina Electrónica."""
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<!-- PLACEHOLDER - Not a valid DIAN document -->
<NominaIndividual>
    <NumeroDocumento>{record.name}</NumeroDocumento>
    <TipoDocumento>{record.document_type}</TipoDocumento>
    <Empleador>
        <NIT>{record.employer_nit}</NIT>
        <Nombre>{record.employer_name}</Nombre>
    </Empleador>
    <Trabajador>
        <NumeroDocumento>{record.employee_document_number}</NumeroDocumento>
    </Trabajador>
    <Periodo>
        <FechaIngreso>{record.period_start}</FechaIngreso>
        <FechaRetiro>{record.period_end}</FechaRetiro>
    </Periodo>
    <DevengadosTotal>{record.total_earnings}</DevengadosTotal>
    <DeduccionesTotal>{record.total_deductions}</DeduccionesTotal>
    <ComprobanteTotal>{record.net_pay}</ComprobanteTotal>
</NominaIndividual>"""

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_reset_draft(self):
        self.write({'state': 'draft', 'xml_content': False})
