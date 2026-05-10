import base64
import csv
import io
import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AccountMoveImportWizard(models.TransientModel):
    _name = 'account.move.import.wizard'
    _description = 'Importar Líneas de Asiento Contable desde CSV/Excel'

    move_id = fields.Many2one(
        'account.move',
        string='Asiento Contable',
        required=True,
    )
    import_file = fields.Binary(
        string='Archivo',
        required=True,
        help='Suba un archivo CSV o Excel con líneas de asiento contable.',
    )
    import_file_name = fields.Char(string='Nombre de Archivo')
    clear_existing = fields.Boolean(
        string='Limpiar Líneas Existentes',
        default=False,
        help='Si está marcado, las líneas existentes del asiento se eliminarán antes de importar.',
    )

    def _parse_csv(self, file_content):
        """Parse CSV content and return list of dicts."""
        try:
            text = file_content.decode('utf-8-sig')
        except UnicodeDecodeError:
            text = file_content.decode('latin-1')
        reader = csv.DictReader(io.StringIO(text))
        return list(reader)

    def _parse_xlsx(self, file_content):
        """Parse XLSX content and return list of dicts."""
        try:
            import openpyxl
        except ImportError:
            raise UserError(_('La librería openpyxl es necesaria para importar archivos Excel. Instálela con: pip install openpyxl'))

        wb = openpyxl.load_workbook(io.BytesIO(file_content), read_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            return []
        headers = [str(h).strip() if h else '' for h in rows[0]]
        result = []
        for row in rows[1:]:
            row_dict = {}
            for idx, header in enumerate(headers):
                row_dict[header] = row[idx] if idx < len(row) else ''
            result.append(row_dict)
        return result

    def _find_account(self, code):
        """Find account by code."""
        if not code:
            return False
        code = str(code).strip()
        account = self.env['account.account'].search([
            ('code', '=', code),
            ('company_ids', 'parent_of', self.env.company.id),
        ], limit=1)
        if not account:
            raise UserError(_('No se encontró la cuenta con código "%s".', code))
        return account.id

    def _find_cost_center(self, code):
        """Find cost center by code."""
        if not code:
            return False
        code = str(code).strip()
        cc = self.env['co.cost.center'].search([
            ('code', '=', code),
            ('code_type', '=', 'detail'),
            ('company_id', '=', self.env.company.id),
        ], limit=1)
        return cc.id if cc else False

    def _find_item_code(self, code):
        """Find item code by code."""
        if not code:
            return False
        code = str(code).strip()
        item = self.env['co.item.code'].search([
            ('code', '=', code),
            ('code_type', '=', 'detail'),
            ('company_id', '=', self.env.company.id),
        ], limit=1)
        return item.id if item else False

    def _find_business_unit(self, code):
        """Find business unit by code."""
        if not code:
            return False
        code = str(code).strip()
        bu = self.env['co.business.unit'].search([
            ('code', '=', code),
            ('company_id', '=', self.env.company.id),
        ], limit=1)
        return bu.id if bu else False

    def _find_partner(self, name):
        """Find partner by name."""
        if not name:
            return False
        name = str(name).strip()
        partner = self.env['res.partner'].search([
            '|', ('name', 'ilike', name), ('vat', '=', name),
        ], limit=1)
        return partner.id if partner else False

    def action_import(self):
        self.ensure_one()
        if not self.import_file:
            raise UserError(_('Por favor suba un archivo.'))

        file_content = base64.b64decode(self.import_file)
        file_name = (self.import_file_name or '').lower()

        if file_name.endswith('.xlsx') or file_name.endswith('.xls'):
            rows = self._parse_xlsx(file_content)
        elif file_name.endswith('.csv'):
            rows = self._parse_csv(file_content)
        else:
            raise UserError(_('Formato de archivo no soportado. Por favor use CSV o XLSX.'))

        if not rows:
            raise UserError(_('El archivo está vacío o no tiene filas de datos.'))

        move = self.move_id
        if move.state != 'draft':
            raise UserError(_('Solo puede importar líneas en asientos contables en estado borrador.'))

        line_vals_list = []
        for idx, row in enumerate(rows, 1):
            account_code = row.get('Código de Cuenta', '')
            if not account_code:
                continue

            debit = float(row.get('Débito', 0) or 0)
            credit = float(row.get('Crédito', 0) or 0)

            vals = {
                'account_id': self._find_account(account_code),
                'name': row.get('Etiqueta', '') or '',
                'partner_id': self._find_partner(row.get('Tercero', '')),
                'cost_center_id': self._find_cost_center(row.get('Código Centro de Costo', '')),
                'item_code_id': self._find_item_code(row.get('Código de Ítem', '')),
                'auxiliar_abierto': row.get('Auxiliar Abierto', '') or '',
                'business_unit_id': self._find_business_unit(row.get('Código Unidad de Negocio', '')),
                'debit': debit,
                'credit': credit,
            }
            line_vals_list.append((0, 0, vals))

        if not line_vals_list:
            raise UserError(_('No se encontraron líneas válidas en el archivo.'))

        if self.clear_existing:
            move.line_ids = [(5, 0, 0)]

        move.write({'line_ids': line_vals_list})

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Importación Exitosa'),
                'message': _('%d líneas importadas en %s.', len(line_vals_list), move.name or _('Nuevo')),
                'type': 'success',
                'sticky': False,
                'next': {
                    'type': 'ir.actions.act_window',
                    'res_model': 'account.move',
                    'res_id': move.id,
                    'views': [(False, 'form')],
                    'target': 'current',
                },
            },
        }
