import base64
import csv
import io
import logging
import zipfile
from datetime import date

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

# NIT check-digit weights
_NIT_WEIGHTS = [3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71]


def compute_nit_check_digit(nit_str):
    """Compute Colombian NIT check digit (digito de verificacion)."""
    if not nit_str:
        return ''
    digits = [int(c) for c in nit_str if c.isdigit()]
    if not digits:
        return ''
    digits_reversed = list(reversed(digits))
    total = sum(d * w for d, w in zip(digits_reversed, _NIT_WEIGHTS))
    remainder = total % 11
    if remainder == 0:
        return '0'
    elif remainder == 1:
        return '1'
    else:
        return str(11 - remainder)


class CoExogenaReport(models.Model):
    """Reporte principal de Informacion Exogena."""

    _name = 'co.exogena.report'
    _description = 'Reporte Exogena DIAN'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'fiscal_year desc, create_date desc'

    name = fields.Char(
        string='Nombre',
        compute='_compute_name',
        store=True,
        readonly=True,
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Compania',
        required=True,
        default=lambda self: self.env.company,
        tracking=True,
    )
    fiscal_year = fields.Integer(
        string='Ano gravable',
        required=True,
        default=lambda self: date.today().year - 1,
        tracking=True,
    )
    date_from = fields.Date(
        string='Fecha desde',
        compute='_compute_dates',
        store=True,
        readonly=True,
    )
    date_to = fields.Date(
        string='Fecha hasta',
        compute='_compute_dates',
        store=True,
        readonly=True,
    )
    company_nit = fields.Char(
        string='NIT',
        compute='_compute_company_info',
        store=True,
    )
    company_nit_dv = fields.Char(
        string='DV',
        compute='_compute_company_info',
        store=True,
    )
    company_name_report = fields.Char(
        string='Razon social',
        compute='_compute_company_info',
        store=True,
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Borrador'),
            ('generated', 'Generado'),
            ('validated', 'Validado'),
            ('error', 'Con errores'),
        ],
        string='Estado',
        default='draft',
        tracking=True,
        required=True,
    )
    format_ids = fields.One2many(
        comodel_name='co.exogena.format',
        inverse_name='report_id',
        string='Formatos',
    )
    format_count = fields.Integer(
        string='Formatos generados',
        compute='_compute_format_count',
    )
    zip_file = fields.Binary(
        string='Archivo ZIP',
        attachment=True,
    )
    zip_filename = fields.Char(
        string='Nombre archivo ZIP',
    )
    notes = fields.Html(
        string='Notas',
    )
    validation_log = fields.Text(
        string='Log de validacion',
        readonly=True,
    )

    _sql_constraints = [
        (
            'company_year_uniq',
            'UNIQUE(company_id, fiscal_year)',
            'Ya existe un reporte Exogena para esta compania y ano gravable.',
        ),
    ]

    @api.depends('fiscal_year', 'company_id')
    def _compute_name(self):
        for rec in self:
            company = rec.company_id.name or ''
            rec.name = f"Exogena {rec.fiscal_year} - {company}"

    @api.depends('fiscal_year')
    def _compute_dates(self):
        for rec in self:
            year = rec.fiscal_year or date.today().year - 1
            rec.date_from = date(year, 1, 1)
            rec.date_to = date(year, 12, 31)

    @api.depends('company_id')
    def _compute_company_info(self):
        for rec in self:
            partner = rec.company_id.partner_id
            vat = partner.vat or ''
            # Remove country prefix if present (e.g., CO900123456)
            nit_raw = vat.replace('CO', '').replace('co', '').strip()
            nit_clean = ''.join(c for c in nit_raw if c.isdigit())
            rec.company_nit = nit_clean
            rec.company_nit_dv = compute_nit_check_digit(nit_clean)
            rec.company_name_report = rec.company_id.name or ''

    @api.depends('format_ids')
    def _compute_format_count(self):
        for rec in self:
            rec.format_count = len(rec.format_ids)

    @api.constrains('fiscal_year')
    def _check_fiscal_year(self):
        current_year = date.today().year
        for rec in self:
            if rec.fiscal_year < 2000 or rec.fiscal_year > current_year:
                raise ValidationError(
                    _(
                        'El ano gravable debe estar entre 2000 y %s.',
                        current_year,
                    )
                )

    def action_generate(self):
        """Open the generation wizard."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Generar Exogena'),
            'res_model': 'co.exogena.generate.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_report_id': self.id,
                'default_fiscal_year': self.fiscal_year,
            },
        }

    def action_validate(self):
        """Validate generated formats for consistency."""
        self.ensure_one()
        if self.state != 'generated':
            raise UserError(_('Solo se pueden validar reportes en estado Generado.'))
        errors = []
        warnings = []

        # 1. Validate NIT check digits on all lines
        for fmt in self.format_ids:
            for line in fmt.line_ids:
                if line.partner_nit:
                    expected_dv = compute_nit_check_digit(line.partner_nit)
                    if line.partner_nit_dv and line.partner_nit_dv != expected_dv:
                        errors.append(
                            f"Formato {fmt.format_code} - Linea {line.partner_name}: "
                            f"DV esperado {expected_dv}, encontrado {line.partner_nit_dv}"
                        )

        # 2. Validate no negative amounts where not allowed
        no_neg_formats = ['1001', '1005', '1006', '1007', '1008', '1009', '1010']
        for fmt in self.format_ids:
            if fmt.format_code in no_neg_formats:
                for line in fmt.line_ids:
                    if line.amount < 0:
                        errors.append(
                            f"Formato {fmt.format_code} - {line.partner_name}: "
                            f"Monto negativo ({line.amount:,.2f}) no permitido."
                        )

        # 3. Cross-reference: 1001 payments should have matching 1003 retentions
        fmt_1001 = self.format_ids.filtered(lambda f: f.format_code == '1001')
        fmt_1003 = self.format_ids.filtered(lambda f: f.format_code == '1003')
        if fmt_1001 and fmt_1003:
            nits_1001 = set(fmt_1001.line_ids.mapped('partner_nit'))
            nits_1003 = set(fmt_1003.line_ids.mapped('partner_nit'))
            nits_with_retention_1001 = set(
                fmt_1001.line_ids.filtered(lambda l: l.retention_amount > 0).mapped('partner_nit')
            )
            missing = nits_with_retention_1001 - nits_1003
            if missing:
                warnings.append(
                    f"Formato 1001 tiene {len(missing)} tercero(s) con retencion "
                    f"sin linea correspondiente en Formato 1003."
                )

        # 4. Validate company NIT
        if not self.company_nit:
            errors.append("La compania no tiene NIT configurado.")

        log_parts = []
        if errors:
            log_parts.append("ERRORES:\n" + "\n".join(f"  - {e}" for e in errors))
        if warnings:
            log_parts.append("ADVERTENCIAS:\n" + "\n".join(f"  - {w}" for w in warnings))
        if not errors and not warnings:
            log_parts.append("Validacion exitosa. No se encontraron errores ni advertencias.")

        self.validation_log = "\n\n".join(log_parts)
        self.state = 'error' if errors else 'validated'
        return True

    def action_reset_draft(self):
        """Reset report to draft and delete generated data."""
        self.ensure_one()
        self.format_ids.unlink()
        self.write({
            'state': 'draft',
            'zip_file': False,
            'zip_filename': False,
            'validation_log': False,
        })

    def action_download_zip(self):
        """Generate and download ZIP with all CSV files."""
        self.ensure_one()
        if not self.format_ids:
            raise UserError(_('No hay formatos generados para descargar.'))

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            for fmt in self.format_ids:
                csv_content = fmt._generate_csv_content()
                filename = f"formato_{fmt.format_code}_{self.fiscal_year}.csv"
                zf.writestr(filename, csv_content)

        zip_data = base64.b64encode(zip_buffer.getvalue())
        zip_name = f"exogena_{self.company_nit}_{self.fiscal_year}.zip"

        self.write({
            'zip_file': zip_data,
            'zip_filename': zip_name,
        })

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{self._name}/{self.id}/zip_file/{zip_name}?download=true',
            'target': 'self',
        }

    def action_view_formats(self):
        """Open formats tree view."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Formatos Exogena'),
            'res_model': 'co.exogena.format',
            'view_mode': 'list,form',
            'domain': [('report_id', '=', self.id)],
            'context': {'default_report_id': self.id},
        }
