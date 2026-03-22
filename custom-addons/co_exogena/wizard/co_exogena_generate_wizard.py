import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

ALL_FORMATS = [
    ('1001', '1001 - Pagos y abonos en cuenta'),
    ('1003', '1003 - Retenciones en la fuente'),
    ('1005', '1005 - IVA descontable'),
    ('1006', '1006 - IVA generado'),
    ('1007', '1007 - Ingresos recibidos'),
    ('1008', '1008 - Cuentas por cobrar'),
    ('1009', '1009 - Cuentas por pagar'),
    ('1010', '1010 - Socios y accionistas'),
    ('1012', '1012 - Declaraciones tributarias'),
]


class CoExogenaGenerateWizard(models.TransientModel):
    """Wizard para generar formatos de Exogena."""

    _name = 'co.exogena.generate.wizard'
    _description = 'Generar Exogena'

    report_id = fields.Many2one(
        comodel_name='co.exogena.report',
        string='Reporte',
        required=True,
    )
    fiscal_year = fields.Integer(
        related='report_id.fiscal_year',
        string='Ano gravable',
        readonly=True,
    )
    company_id = fields.Many2one(
        related='report_id.company_id',
        string='Compania',
        readonly=True,
    )
    generate_1001 = fields.Boolean(string='1001 - Pagos y abonos', default=True)
    generate_1003 = fields.Boolean(string='1003 - Retenciones fuente', default=True)
    generate_1005 = fields.Boolean(string='1005 - IVA descontable', default=True)
    generate_1006 = fields.Boolean(string='1006 - IVA generado', default=True)
    generate_1007 = fields.Boolean(string='1007 - Ingresos recibidos', default=True)
    generate_1008 = fields.Boolean(string='1008 - Cuentas por cobrar', default=True)
    generate_1009 = fields.Boolean(string='1009 - Cuentas por pagar', default=True)
    generate_1010 = fields.Boolean(string='1010 - Socios y accionistas', default=False)
    generate_1012 = fields.Boolean(string='1012 - Declaraciones tributarias', default=True)
    min_amount_1001 = fields.Float(string='Cuantia minima 1001', default=100000)
    min_amount_1007 = fields.Float(string='Cuantia minima 1007', default=500000)
    min_amount_1008 = fields.Float(string='Cuantia minima 1008', default=500000)
    min_amount_1009 = fields.Float(string='Cuantia minima 1009', default=500000)
    overwrite_existing = fields.Boolean(
        string='Sobrescribir formatos existentes',
        default=True,
        help='Si esta activo, elimina los formatos existentes antes de generar nuevos.',
    )

    def action_generate(self):
        """Main generation method."""
        self.ensure_one()
        report = self.report_id

        if not report.company_nit:
            raise UserError(
                _('La compania %s no tiene NIT configurado. '
                  'Configure el NIT en Ajustes > Companias.', report.company_id.name)
            )

        if self.overwrite_existing:
            report.format_ids.unlink()

        selected = []
        for code, _label in ALL_FORMATS:
            if getattr(self, f'generate_{code}', False):
                selected.append(code)

        if not selected:
            raise UserError(_('Debe seleccionar al menos un formato para generar.'))

        date_from = report.date_from
        date_to = report.date_to
        company = report.company_id

        FormatModel = self.env['co.exogena.format']
        LineModel = self.env['co.exogena.line']

        generated_count = 0
        for code in selected:
            _logger.info("Generating Exogena format %s for %s year %s",
                         code, company.name, report.fiscal_year)

            # Create format record
            fmt = FormatModel.create({
                'report_id': report.id,
                'format_code': code,
            })

            method_name = f'_generate_{code}'
            method = getattr(self, method_name, None)
            if method:
                lines_data = method(report, date_from, date_to, company)
                for vals in lines_data:
                    vals['format_id'] = fmt.id
                    LineModel.create(vals)
                generated_count += 1
            else:
                _logger.warning("No generation method for format %s", code)

        report.state = 'generated'

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Exogena generada'),
                'message': _('Se generaron %s formato(s) exitosamente.', generated_count),
                'type': 'success',
                'sticky': False,
                'next': {
                    'type': 'ir.actions.act_window',
                    'res_model': 'co.exogena.report',
                    'res_id': report.id,
                    'view_mode': 'form',
                    'target': 'current',
                },
            },
        }

    # -------------------------------------------------------------------------
    # Helper methods
    # -------------------------------------------------------------------------

    def _get_posted_moves(self, date_from, date_to, company, move_types=None):
        """Get posted account.move records in the period."""
        domain = [
            ('company_id', '=', company.id),
            ('date', '>=', date_from),
            ('date', '<=', date_to),
            ('state', '=', 'posted'),
        ]
        if move_types:
            domain.append(('move_type', 'in', move_types))
        return self.env['account.move'].search(domain)

    def _get_move_lines(self, date_from, date_to, company, domain_extra=None):
        """Get account.move.line records for posted moves in the period."""
        domain = [
            ('company_id', '=', company.id),
            ('date', '>=', date_from),
            ('date', '<=', date_to),
            ('parent_state', '=', 'posted'),
        ]
        if domain_extra:
            domain.extend(domain_extra)
        return self.env['account.move.line'].search(domain)

    def _partner_vals(self, partner):
        """Extract partner data dict using the Line model helper."""
        return self.env['co.exogena.line']._extract_partner_data(partner)

    def _apply_min_threshold(self, grouped, min_amount):
        """Apply minimum amount threshold. Below-threshold entries are aggregated
        under NIT 222222222 (cuantias menores)."""
        if min_amount <= 0:
            return grouped

        result = {}
        minor_total = {}

        for key, vals in grouped.items():
            if abs(vals.get('amount', 0)) < min_amount:
                # Accumulate into cuantias menores
                concept = vals.get('concept_code', '')
                if concept not in minor_total:
                    minor_total[concept] = {
                        'amount': 0,
                        'base_amount': 0,
                        'retention_amount': 0,
                        'vat_amount': 0,
                    }
                minor_total[concept]['amount'] += vals.get('amount', 0)
                minor_total[concept]['base_amount'] += vals.get('base_amount', 0)
                minor_total[concept]['retention_amount'] += vals.get('retention_amount', 0)
                minor_total[concept]['vat_amount'] += vals.get('vat_amount', 0)
            else:
                result[key] = vals

        # Add cuantias menores lines
        if minor_total:
            minor_partner = self._partner_vals(False)  # NIT 222222222
            for concept, totals in minor_total.items():
                key = ('222222222', concept)
                vals = dict(minor_partner)
                vals.update({
                    'concept_code': concept,
                    'amount': totals['amount'],
                    'base_amount': totals['base_amount'],
                    'retention_amount': totals['retention_amount'],
                    'vat_amount': totals['vat_amount'],
                })
                result[key] = vals

        return result

    # -------------------------------------------------------------------------
    # Format generation methods
    # -------------------------------------------------------------------------

    def _generate_1001(self, report, date_from, date_to, company):
        """Formato 1001 - Pagos y abonos en cuenta a terceros.
        Extracts from vendor bills and payments."""
        lines = self._get_move_lines(date_from, date_to, company, [
            ('move_id.move_type', 'in', ['in_invoice', 'in_refund']),
        ])

        grouped = {}
        for ml in lines:
            partner = ml.partner_id
            if not partner:
                continue
            nit = (partner.vat or '').replace('CO', '').replace('co', '').strip()
            nit_clean = ''.join(c for c in nit if c.isdigit())
            concept = '5001'  # Default: compras

            # Determine concept based on account
            account_code = ml.account_id.code or ''
            if account_code.startswith('51'):
                concept = '5002'  # Gastos operacionales
            elif account_code.startswith('52'):
                concept = '5003'  # Gastos no operacionales
            elif account_code.startswith('53'):
                concept = '5004'  # Otros gastos

            key = (nit_clean or 'NO_NIT', concept)
            if key not in grouped:
                pvals = self._partner_vals(partner)
                pvals['concept_code'] = concept
                pvals['amount'] = 0
                pvals['base_amount'] = 0
                pvals['retention_amount'] = 0
                pvals['vat_amount'] = 0
                grouped[key] = pvals

            # Debit amounts = payment/expense; credit on refund
            if ml.debit > 0:
                grouped[key]['amount'] += ml.debit
            elif ml.credit > 0 and ml.move_id.move_type == 'in_refund':
                grouped[key]['amount'] -= ml.credit

        # Extract withholding tax lines
        tax_lines = self._get_move_lines(date_from, date_to, company, [
            ('move_id.move_type', 'in', ['in_invoice', 'in_refund']),
            ('tax_line_id', '!=', False),
        ])
        for tl in tax_lines:
            partner = tl.partner_id
            if not partner:
                continue
            nit = (partner.vat or '').replace('CO', '').replace('co', '').strip()
            nit_clean = ''.join(c for c in nit if c.isdigit())
            tax = tl.tax_line_id

            # Identify retention taxes (typically negative/credit)
            tax_name = (tax.name or '').lower()
            is_retention = any(kw in tax_name for kw in ['retefu', 'retencion', 'rete iva', 'rete ica'])
            is_vat = 'iva' in tax_name and 'rete' not in tax_name

            for concept_code in grouped:
                if concept_code[0] == nit_clean:
                    if is_retention:
                        grouped[concept_code]['retention_amount'] += abs(tl.balance)
                        grouped[concept_code]['base_amount'] += abs(tl.tax_base_amount)
                    elif is_vat:
                        grouped[concept_code]['vat_amount'] += abs(tl.balance)
                    break

        grouped = self._apply_min_threshold(grouped, self.min_amount_1001)
        return list(grouped.values())

    def _generate_1003(self, report, date_from, date_to, company):
        """Formato 1003 - Retenciones en la fuente practicadas.
        Extracts retention tax lines from vendor bills."""
        tax_lines = self._get_move_lines(date_from, date_to, company, [
            ('tax_line_id', '!=', False),
        ])

        grouped = {}
        for tl in tax_lines:
            tax = tl.tax_line_id
            tax_name = (tax.name or '').lower()

            # Only retention taxes
            is_retention = any(kw in tax_name for kw in [
                'retefu', 'retencion en la fuente', 'rete fuente',
                'retefuente', 'rete renta',
            ])
            if not is_retention:
                continue

            partner = tl.partner_id
            if not partner:
                continue

            nit = (partner.vat or '').replace('CO', '').replace('co', '').strip()
            nit_clean = ''.join(c for c in nit if c.isdigit())

            # Concept based on tax type
            concept = '1301'  # Default: retencion renta

            key = (nit_clean or 'NO_NIT', concept)
            if key not in grouped:
                pvals = self._partner_vals(partner)
                pvals['concept_code'] = concept
                pvals['base_amount'] = 0
                pvals['retention_amount'] = 0
                pvals['amount'] = 0
                grouped[key] = pvals

            grouped[key]['base_amount'] += abs(tl.tax_base_amount)
            grouped[key]['retention_amount'] += abs(tl.balance)
            grouped[key]['amount'] += abs(tl.balance)

        return list(grouped.values())

    def _generate_1005(self, report, date_from, date_to, company):
        """Formato 1005 - IVA descontable en compras.
        Extracts VAT from vendor bills."""
        tax_lines = self._get_move_lines(date_from, date_to, company, [
            ('move_id.move_type', 'in', ['in_invoice', 'in_refund']),
            ('tax_line_id', '!=', False),
        ])

        grouped = {}
        for tl in tax_lines:
            tax = tl.tax_line_id
            tax_name = (tax.name or '').lower()

            # Only IVA (VAT), not retention
            is_vat = 'iva' in tax_name and 'rete' not in tax_name
            if not is_vat:
                continue

            partner = tl.partner_id
            if not partner:
                continue

            nit = (partner.vat or '').replace('CO', '').replace('co', '').strip()
            nit_clean = ''.join(c for c in nit if c.isdigit())

            key = nit_clean or 'NO_NIT'
            if key not in grouped:
                pvals = self._partner_vals(partner)
                pvals['amount'] = 0
                pvals['vat_amount'] = 0
                pvals['base_amount'] = 0
                pvals['retention_amount'] = 0
                pvals['concept_code'] = ''
                grouped[key] = pvals

            grouped[key]['amount'] += abs(tl.tax_base_amount)
            grouped[key]['vat_amount'] += abs(tl.balance)

        return list(grouped.values())

    def _generate_1006(self, report, date_from, date_to, company):
        """Formato 1006 - IVA generado en ventas.
        Extracts VAT from customer invoices."""
        tax_lines = self._get_move_lines(date_from, date_to, company, [
            ('move_id.move_type', 'in', ['out_invoice', 'out_refund']),
            ('tax_line_id', '!=', False),
        ])

        grouped = {}
        for tl in tax_lines:
            tax = tl.tax_line_id
            tax_name = (tax.name or '').lower()

            is_vat = 'iva' in tax_name and 'rete' not in tax_name
            if not is_vat:
                continue

            partner = tl.partner_id
            if not partner:
                continue

            nit = (partner.vat or '').replace('CO', '').replace('co', '').strip()
            nit_clean = ''.join(c for c in nit if c.isdigit())

            key = nit_clean or 'NO_NIT'
            if key not in grouped:
                pvals = self._partner_vals(partner)
                pvals['amount'] = 0
                pvals['vat_amount'] = 0
                pvals['base_amount'] = 0
                pvals['retention_amount'] = 0
                pvals['concept_code'] = ''
                grouped[key] = pvals

            grouped[key]['amount'] += abs(tl.tax_base_amount)
            grouped[key]['vat_amount'] += abs(tl.balance)

        return list(grouped.values())

    def _generate_1007(self, report, date_from, date_to, company):
        """Formato 1007 - Ingresos recibidos de terceros.
        Extracts income from customer invoices."""
        lines = self._get_move_lines(date_from, date_to, company, [
            ('move_id.move_type', 'in', ['out_invoice', 'out_refund']),
            ('account_id.account_type', '=', 'income'),
        ])

        grouped = {}
        for ml in lines:
            partner = ml.partner_id
            if not partner:
                continue

            nit = (partner.vat or '').replace('CO', '').replace('co', '').strip()
            nit_clean = ''.join(c for c in nit if c.isdigit())

            # Concept based on account type
            account_code = ml.account_id.code or ''
            concept = '4001'  # Default: ingresos operacionales
            if account_code.startswith('42'):
                concept = '4002'  # Ingresos no operacionales

            key = (nit_clean or 'NO_NIT', concept)
            if key not in grouped:
                pvals = self._partner_vals(partner)
                pvals['concept_code'] = concept
                pvals['amount'] = 0
                pvals['base_amount'] = 0
                pvals['retention_amount'] = 0
                pvals['vat_amount'] = 0
                grouped[key] = pvals

            # Credit = income
            if ml.credit > 0:
                grouped[key]['amount'] += ml.credit
            elif ml.debit > 0 and ml.move_id.move_type == 'out_refund':
                grouped[key]['amount'] -= ml.debit

        grouped = self._apply_min_threshold(grouped, self.min_amount_1007)
        return list(grouped.values())

    def _generate_1008(self, report, date_from, date_to, company):
        """Formato 1008 - Saldos de cuentas por cobrar al 31 de diciembre.
        Uses receivable balance at year end."""
        # Get receivable accounts balance at year end
        lines = self.env['account.move.line'].search([
            ('company_id', '=', company.id),
            ('date', '<=', date_to),
            ('parent_state', '=', 'posted'),
            ('account_id.account_type', '=', 'asset_receivable'),
        ])

        grouped = {}
        for ml in lines:
            partner = ml.partner_id
            if not partner:
                continue

            nit = (partner.vat or '').replace('CO', '').replace('co', '').strip()
            nit_clean = ''.join(c for c in nit if c.isdigit())

            key = nit_clean or 'NO_NIT'
            if key not in grouped:
                pvals = self._partner_vals(partner)
                pvals['amount'] = 0
                pvals['base_amount'] = 0
                pvals['retention_amount'] = 0
                pvals['vat_amount'] = 0
                pvals['concept_code'] = ''
                grouped[key] = pvals

            grouped[key]['amount'] += ml.balance  # debit - credit

        # Remove zero/negative balances (only report positive receivables)
        grouped = {k: v for k, v in grouped.items() if v['amount'] > 0}

        grouped = self._apply_min_threshold(grouped, self.min_amount_1008)
        return list(grouped.values())

    def _generate_1009(self, report, date_from, date_to, company):
        """Formato 1009 - Saldos de cuentas por pagar al 31 de diciembre.
        Uses payable balance at year end."""
        lines = self.env['account.move.line'].search([
            ('company_id', '=', company.id),
            ('date', '<=', date_to),
            ('parent_state', '=', 'posted'),
            ('account_id.account_type', '=', 'liability_payable'),
        ])

        grouped = {}
        for ml in lines:
            partner = ml.partner_id
            if not partner:
                continue

            nit = (partner.vat or '').replace('CO', '').replace('co', '').strip()
            nit_clean = ''.join(c for c in nit if c.isdigit())

            key = nit_clean or 'NO_NIT'
            if key not in grouped:
                pvals = self._partner_vals(partner)
                pvals['amount'] = 0
                pvals['base_amount'] = 0
                pvals['retention_amount'] = 0
                pvals['vat_amount'] = 0
                pvals['concept_code'] = ''
                grouped[key] = pvals

            grouped[key]['amount'] += abs(ml.balance)  # payable balances are negative

        # Remove zero balances
        grouped = {k: v for k, v in grouped.items() if v['amount'] > 0}

        grouped = self._apply_min_threshold(grouped, self.min_amount_1009)
        return list(grouped.values())

    def _generate_1010(self, report, date_from, date_to, company):
        """Formato 1010 - Socios y accionistas.
        This format requires manual partner data or a custom equity model.
        We extract from equity accounts (PUC class 3)."""
        lines = self.env['account.move.line'].search([
            ('company_id', '=', company.id),
            ('date', '<=', date_to),
            ('parent_state', '=', 'posted'),
            ('account_id.account_type', '=', 'equity'),
        ])

        # Group by partner
        grouped = {}
        total_equity = 0
        for ml in lines:
            partner = ml.partner_id
            if not partner:
                continue

            nit = (partner.vat or '').replace('CO', '').replace('co', '').strip()
            nit_clean = ''.join(c for c in nit if c.isdigit())

            key = nit_clean or 'NO_NIT'
            if key not in grouped:
                pvals = self._partner_vals(partner)
                pvals['amount'] = 0
                pvals['participation_pct'] = 0
                pvals['base_amount'] = 0
                pvals['retention_amount'] = 0
                pvals['vat_amount'] = 0
                pvals['concept_code'] = ''
                grouped[key] = pvals

            amount = abs(ml.balance)
            grouped[key]['amount'] += amount
            total_equity += amount

        # Calculate participation percentage
        if total_equity > 0:
            for vals in grouped.values():
                vals['participation_pct'] = (vals['amount'] / total_equity) * 100

        return list(grouped.values())

    def _generate_1012(self, report, date_from, date_to, company):
        """Formato 1012 - Declaraciones tributarias (resumen).
        Summarizes tax declarations for the period."""
        # Get all tax lines for the period
        tax_lines = self._get_move_lines(date_from, date_to, company, [
            ('tax_line_id', '!=', False),
        ])

        grouped = {}
        for tl in tax_lines:
            tax = tl.tax_line_id
            tax_name = (tax.name or '').lower()

            # Classify tax type
            if 'iva' in tax_name and 'rete' not in tax_name:
                concept = '0001'  # IVA
            elif 'retefu' in tax_name or 'retencion en la fuente' in tax_name or 'rete fuente' in tax_name:
                concept = '0002'  # Retencion en la fuente
            elif 'rete iva' in tax_name:
                concept = '0003'  # Retencion de IVA
            elif 'ica' in tax_name or 'rete ica' in tax_name:
                concept = '0004'  # ICA
            elif 'timbre' in tax_name:
                concept = '0005'  # Timbre
            else:
                concept = '0099'  # Otros impuestos

            if concept not in grouped:
                grouped[concept] = {
                    'concept_code': concept,
                    'base_amount': 0,
                    'amount': 0,
                    'retention_amount': 0,
                    'vat_amount': 0,
                    'partner_name': f'Declaracion concepto {concept}',
                    'partner_nit': '',
                    'partner_nit_dv': '',
                    'partner_doc_type': '',
                    'partner_is_company': False,
                    'partner_address': '',
                    'partner_dept_code': '',
                    'partner_mun_code': '',
                    'partner_country_code': 'CO',
                }

            grouped[concept]['base_amount'] += abs(tl.tax_base_amount)
            grouped[concept]['amount'] += abs(tl.balance)

        return list(grouped.values())
