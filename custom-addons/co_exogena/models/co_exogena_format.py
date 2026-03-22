import csv
import io
import logging

from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)

# CSV column definitions per DIAN format
FORMAT_COLUMNS = {
    '1001': [
        'Concepto', 'Tipo documento', 'Numero identificacion',
        'Digito verificacion', 'Primer apellido', 'Segundo apellido',
        'Primer nombre', 'Otros nombres', 'Razon social',
        'Direccion', 'Codigo departamento', 'Codigo municipio',
        'Pago o abono en cuenta', 'Valor base retencion',
        'Valor retencion', 'Valor IVA', 'Pais',
    ],
    '1003': [
        'Concepto', 'Tipo documento', 'Numero identificacion',
        'Digito verificacion', 'Primer apellido', 'Segundo apellido',
        'Primer nombre', 'Otros nombres', 'Razon social',
        'Direccion', 'Codigo departamento', 'Codigo municipio',
        'Base retencion', 'Valor retencion', 'Pais',
    ],
    '1005': [
        'Tipo documento', 'Numero identificacion',
        'Digito verificacion', 'Primer apellido', 'Segundo apellido',
        'Primer nombre', 'Otros nombres', 'Razon social',
        'Valor operacion', 'Valor IVA', 'Pais',
    ],
    '1006': [
        'Tipo documento', 'Numero identificacion',
        'Digito verificacion', 'Primer apellido', 'Segundo apellido',
        'Primer nombre', 'Otros nombres', 'Razon social',
        'Valor operacion', 'Valor IVA', 'Pais',
    ],
    '1007': [
        'Concepto', 'Tipo documento', 'Numero identificacion',
        'Digito verificacion', 'Primer apellido', 'Segundo apellido',
        'Primer nombre', 'Otros nombres', 'Razon social',
        'Direccion', 'Codigo departamento', 'Codigo municipio',
        'Valor operacion', 'Pais',
    ],
    '1008': [
        'Tipo documento', 'Numero identificacion',
        'Digito verificacion', 'Primer apellido', 'Segundo apellido',
        'Primer nombre', 'Otros nombres', 'Razon social',
        'Direccion', 'Codigo departamento', 'Codigo municipio',
        'Saldo cuentas por cobrar a 31 dic', 'Pais',
    ],
    '1009': [
        'Tipo documento', 'Numero identificacion',
        'Digito verificacion', 'Primer apellido', 'Segundo apellido',
        'Primer nombre', 'Otros nombres', 'Razon social',
        'Direccion', 'Codigo departamento', 'Codigo municipio',
        'Saldo cuentas por pagar a 31 dic', 'Pais',
    ],
    '1010': [
        'Tipo documento', 'Numero identificacion',
        'Digito verificacion', 'Primer apellido', 'Segundo apellido',
        'Primer nombre', 'Otros nombres', 'Razon social',
        'Direccion', 'Codigo departamento', 'Codigo municipio',
        'Valor patrimonial acciones', 'Porcentaje participacion',
        'Pais',
    ],
    '1012': [
        'Concepto', 'Valor base gravable', 'Valor impuesto',
        'Valor retencion',
    ],
}


class CoExogenaFormat(models.Model):
    """Formato individual de Exogena (e.g., 1001, 1003, etc.)."""

    _name = 'co.exogena.format'
    _description = 'Formato Exogena'
    _order = 'format_code'

    name = fields.Char(
        string='Nombre',
        compute='_compute_name',
        store=True,
    )
    report_id = fields.Many2one(
        comodel_name='co.exogena.report',
        string='Reporte',
        required=True,
        ondelete='cascade',
        index=True,
    )
    format_code = fields.Selection(
        selection=[
            ('1001', '1001 - Pagos y abonos en cuenta'),
            ('1003', '1003 - Retenciones en la fuente'),
            ('1005', '1005 - IVA descontable'),
            ('1006', '1006 - IVA generado'),
            ('1007', '1007 - Ingresos recibidos'),
            ('1008', '1008 - Cuentas por cobrar'),
            ('1009', '1009 - Cuentas por pagar'),
            ('1010', '1010 - Socios y accionistas'),
            ('1012', '1012 - Declaraciones tributarias'),
        ],
        string='Formato',
        required=True,
    )
    line_ids = fields.One2many(
        comodel_name='co.exogena.line',
        inverse_name='format_id',
        string='Lineas',
    )
    line_count = fields.Integer(
        string='Lineas',
        compute='_compute_line_count',
    )
    total_amount = fields.Float(
        string='Total monto',
        compute='_compute_totals',
        digits=(16, 2),
    )
    total_base_amount = fields.Float(
        string='Total base',
        compute='_compute_totals',
        digits=(16, 2),
    )
    total_retention = fields.Float(
        string='Total retencion',
        compute='_compute_totals',
        digits=(16, 2),
    )
    total_vat = fields.Float(
        string='Total IVA',
        compute='_compute_totals',
        digits=(16, 2),
    )
    csv_file = fields.Binary(
        string='Archivo CSV',
        attachment=True,
    )
    csv_filename = fields.Char(
        string='Nombre archivo CSV',
    )

    _sql_constraints = [
        (
            'report_format_uniq',
            'UNIQUE(report_id, format_code)',
            'El formato debe ser unico por reporte.',
        ),
    ]

    FORMAT_LABELS = {
        '1001': 'Pagos y abonos en cuenta',
        '1003': 'Retenciones en la fuente',
        '1005': 'IVA descontable',
        '1006': 'IVA generado',
        '1007': 'Ingresos recibidos',
        '1008': 'Cuentas por cobrar',
        '1009': 'Cuentas por pagar',
        '1010': 'Socios y accionistas',
        '1012': 'Declaraciones tributarias',
    }

    @api.depends('format_code')
    def _compute_name(self):
        for rec in self:
            label = self.FORMAT_LABELS.get(rec.format_code, '')
            rec.name = f"Formato {rec.format_code} - {label}"

    @api.depends('line_ids')
    def _compute_line_count(self):
        for rec in self:
            rec.line_count = len(rec.line_ids)

    @api.depends('line_ids.amount', 'line_ids.base_amount', 'line_ids.retention_amount', 'line_ids.vat_amount')
    def _compute_totals(self):
        for rec in self:
            rec.total_amount = sum(rec.line_ids.mapped('amount'))
            rec.total_base_amount = sum(rec.line_ids.mapped('base_amount'))
            rec.total_retention = sum(rec.line_ids.mapped('retention_amount'))
            rec.total_vat = sum(rec.line_ids.mapped('vat_amount'))

    def _get_partner_info(self, line):
        """Extract partner identification fields for CSV row."""
        partner_name = line.partner_name or ''
        # Parse name parts -- simplistic split
        parts = partner_name.strip().split()
        is_company = line.partner_is_company

        if is_company:
            return {
                'primer_apellido': '',
                'segundo_apellido': '',
                'primer_nombre': '',
                'otros_nombres': '',
                'razon_social': partner_name,
            }
        else:
            return {
                'primer_apellido': parts[0] if len(parts) >= 1 else '',
                'segundo_apellido': parts[1] if len(parts) >= 2 else '',
                'primer_nombre': parts[2] if len(parts) >= 3 else (parts[0] if len(parts) == 1 else ''),
                'otros_nombres': ' '.join(parts[3:]) if len(parts) > 3 else '',
                'razon_social': '',
            }

    def _get_doc_type(self, line):
        """Map Odoo l10n_co document types to DIAN codes."""
        # Common mappings
        doc_type = line.partner_doc_type or ''
        mapping = {
            'rut': '31',          # NIT
            'id_document': '13',  # Cedula ciudadania
            'foreign_id': '22',   # Cedula extranjeria
            'passport': '41',     # Pasaporte
            'nit': '31',
            'external_id': '42',  # Documento de identificacion extranjero
        }
        return mapping.get(doc_type, '31')  # Default NIT

    def _line_to_csv_row(self, line):
        """Convert a line record to a CSV row list based on format_code."""
        info = self._get_partner_info(line)
        doc_type = self._get_doc_type(line)
        nit = line.partner_nit or ''
        dv = line.partner_nit_dv or ''
        concept = line.concept_code or ''
        address = line.partner_address or ''
        dept_code = line.partner_dept_code or ''
        mun_code = line.partner_mun_code or ''
        country_code = line.partner_country_code or 'CO'

        def amt(val):
            return f"{val:.2f}" if val else "0.00"

        code = self.format_code
        if code == '1001':
            return [
                concept, doc_type, nit, dv,
                info['primer_apellido'], info['segundo_apellido'],
                info['primer_nombre'], info['otros_nombres'],
                info['razon_social'],
                address, dept_code, mun_code,
                amt(line.amount), amt(line.base_amount),
                amt(line.retention_amount), amt(line.vat_amount),
                country_code,
            ]
        elif code == '1003':
            return [
                concept, doc_type, nit, dv,
                info['primer_apellido'], info['segundo_apellido'],
                info['primer_nombre'], info['otros_nombres'],
                info['razon_social'],
                address, dept_code, mun_code,
                amt(line.base_amount), amt(line.retention_amount),
                country_code,
            ]
        elif code in ('1005', '1006'):
            return [
                doc_type, nit, dv,
                info['primer_apellido'], info['segundo_apellido'],
                info['primer_nombre'], info['otros_nombres'],
                info['razon_social'],
                amt(line.amount), amt(line.vat_amount),
                country_code,
            ]
        elif code == '1007':
            return [
                concept, doc_type, nit, dv,
                info['primer_apellido'], info['segundo_apellido'],
                info['primer_nombre'], info['otros_nombres'],
                info['razon_social'],
                address, dept_code, mun_code,
                amt(line.amount), country_code,
            ]
        elif code in ('1008', '1009'):
            return [
                doc_type, nit, dv,
                info['primer_apellido'], info['segundo_apellido'],
                info['primer_nombre'], info['otros_nombres'],
                info['razon_social'],
                address, dept_code, mun_code,
                amt(line.amount), country_code,
            ]
        elif code == '1010':
            pct = f"{line.participation_pct:.2f}" if line.participation_pct else "0.00"
            return [
                doc_type, nit, dv,
                info['primer_apellido'], info['segundo_apellido'],
                info['primer_nombre'], info['otros_nombres'],
                info['razon_social'],
                address, dept_code, mun_code,
                amt(line.amount), pct, country_code,
            ]
        elif code == '1012':
            return [
                concept, amt(line.base_amount),
                amt(line.amount), amt(line.retention_amount),
            ]
        return []

    def _generate_csv_content(self):
        """Generate CSV string for this format."""
        self.ensure_one()
        output = io.StringIO()
        writer = csv.writer(output, delimiter=';', quoting=csv.QUOTE_MINIMAL)

        columns = FORMAT_COLUMNS.get(self.format_code, [])
        writer.writerow(columns)

        for line in self.line_ids.sorted(lambda l: (l.partner_nit or '', l.concept_code or '')):
            row = self._line_to_csv_row(line)
            writer.writerow(row)

        return output.getvalue()

    def action_download_csv(self):
        """Generate and download individual CSV file."""
        self.ensure_one()
        import base64
        csv_content = self._generate_csv_content()
        csv_data = base64.b64encode(csv_content.encode('utf-8'))
        year = self.report_id.fiscal_year
        filename = f"formato_{self.format_code}_{year}.csv"

        self.write({
            'csv_file': csv_data,
            'csv_filename': filename,
        })

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{self._name}/{self.id}/csv_file/{filename}?download=true',
            'target': 'self',
        }

    def action_view_lines(self):
        """Open lines for this format."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Lineas - %s', self.name),
            'res_model': 'co.exogena.line',
            'view_mode': 'list,form',
            'domain': [('format_id', '=', self.id)],
            'context': {'default_format_id': self.id},
        }
