from odoo import models, fields, api

from .co_exogena_report import compute_nit_check_digit


class CoExogenaLine(models.Model):
    """Linea individual de un formato Exogena."""

    _name = 'co.exogena.line'
    _description = 'Linea Exogena'
    _order = 'partner_nit, concept_code'

    format_id = fields.Many2one(
        comodel_name='co.exogena.format',
        string='Formato',
        required=True,
        ondelete='cascade',
        index=True,
    )
    report_id = fields.Many2one(
        related='format_id.report_id',
        string='Reporte',
        store=True,
        index=True,
    )
    format_code = fields.Selection(
        related='format_id.format_code',
        string='Codigo formato',
        store=True,
    )
    partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Tercero',
        index=True,
    )
    partner_name = fields.Char(
        string='Nombre / Razon social',
    )
    partner_nit = fields.Char(
        string='NIT',
        index=True,
    )
    partner_nit_dv = fields.Char(
        string='DV',
    )
    partner_doc_type = fields.Char(
        string='Tipo documento',
    )
    partner_is_company = fields.Boolean(
        string='Es empresa',
        default=False,
    )
    partner_address = fields.Char(
        string='Direccion',
    )
    partner_dept_code = fields.Char(
        string='Cod. departamento',
    )
    partner_mun_code = fields.Char(
        string='Cod. municipio',
    )
    partner_country_code = fields.Char(
        string='Cod. pais',
        default='CO',
    )
    concept_id = fields.Many2one(
        comodel_name='co.exogena.concept',
        string='Concepto',
    )
    concept_code = fields.Char(
        string='Codigo concepto',
    )
    amount = fields.Float(
        string='Monto',
        digits=(16, 2),
    )
    base_amount = fields.Float(
        string='Base',
        digits=(16, 2),
    )
    retention_amount = fields.Float(
        string='Retencion',
        digits=(16, 2),
    )
    vat_amount = fields.Float(
        string='IVA',
        digits=(16, 2),
    )
    participation_pct = fields.Float(
        string='% Participacion',
        digits=(5, 2),
        help='Porcentaje de participacion (solo para formato 1010).',
    )

    @api.model
    def _extract_partner_data(self, partner):
        """Extract standardized partner data for Exogena lines."""
        if not partner:
            return {
                'partner_id': False,
                'partner_name': 'CUANTIAS MENORES',
                'partner_nit': '222222222',
                'partner_nit_dv': compute_nit_check_digit('222222222'),
                'partner_doc_type': 'nit',
                'partner_is_company': False,
                'partner_address': '',
                'partner_dept_code': '',
                'partner_mun_code': '',
                'partner_country_code': 'CO',
            }

        vat = partner.vat or ''
        nit_raw = vat.replace('CO', '').replace('co', '').strip()
        nit_clean = ''.join(c for c in nit_raw if c.isdigit())

        # Try to get document type from l10n_co fields
        doc_type = 'nit'
        if hasattr(partner, 'l10n_latam_identification_type_id'):
            id_type = partner.l10n_latam_identification_type_id
            if id_type:
                code = (id_type.l10n_co_document_code or id_type.name or '').lower()
                if 'ced' in code or 'cc' in code:
                    doc_type = 'id_document'
                elif 'ext' in code or 'ce' in code:
                    doc_type = 'foreign_id'
                elif 'pas' in code:
                    doc_type = 'passport'
                elif 'nit' in code or 'rut' in code:
                    doc_type = 'nit'

        # Department and municipality codes from l10n_co
        dept_code = ''
        mun_code = ''
        if partner.state_id and hasattr(partner.state_id, 'code'):
            dept_code = partner.state_id.code or ''
        if hasattr(partner, 'l10n_co_edi_large_taxpayer'):
            # Try city code from various possible fields
            pass
        city = partner.city or ''

        country_code = partner.country_id.code or 'CO' if partner.country_id else 'CO'

        return {
            'partner_id': partner.id,
            'partner_name': partner.name or '',
            'partner_nit': nit_clean,
            'partner_nit_dv': compute_nit_check_digit(nit_clean),
            'partner_doc_type': doc_type,
            'partner_is_company': partner.is_company,
            'partner_address': (partner.street or ''),
            'partner_dept_code': dept_code,
            'partner_mun_code': mun_code,
            'partner_country_code': country_code,
        }
