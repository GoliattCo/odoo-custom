import base64
import csv
import io
import logging
from datetime import datetime

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class CoBankImportWizard(models.TransientModel):
    _name = 'co.bank.import.wizard'
    _description = 'Import Colombian Bank Statement File'

    journal_id = fields.Many2one(
        'account.journal',
        string='Bank Journal',
        required=True,
        domain=[('type', '=', 'bank')],
    )
    format_id = fields.Many2one(
        'co.bank.format',
        string='Bank Format',
        required=True,
    )
    file_data = fields.Binary(
        string='Bank File',
        required=True,
        help='Upload the flat file (CSV or TXT) from your bank.',
    )
    filename = fields.Char(string='Filename')
    auto_reconcile = fields.Boolean(
        string='Auto-Reconcile After Import',
        default=True,
    )

    def action_import(self):
        """Parse the uploaded file and create a statement with lines."""
        self.ensure_one()
        if not self.file_data:
            raise UserError(_('Please upload a file.'))

        fmt = self.format_id
        raw = base64.b64decode(self.file_data)

        # Decode with the configured encoding, falling back gracefully
        content = self._decode_file(raw, fmt.encoding)

        # Parse CSV
        lines_data = self._parse_csv(content, fmt)
        if not lines_data:
            raise UserError(_('No data lines found in the file. Check the format configuration.'))

        # Create statement
        dates = [ld['date'] for ld in lines_data if ld.get('date')]
        statement_vals = {
            'journal_id': self.journal_id.id,
            'format_id': fmt.id,
            'filename': self.filename or 'unknown',
            'date_start': min(dates) if dates else False,
            'date_end': max(dates) if dates else False,
            'balance_start': lines_data[0].get('balance', 0.0) - lines_data[0].get('amount', 0.0)
            if lines_data else 0.0,
            'balance_end': lines_data[-1].get('balance', 0.0) if lines_data else 0.0,
            'state': 'imported',
        }
        statement = self.env['co.bank.statement.import'].create(statement_vals)

        # Create lines
        line_vals_list = []
        for seq, ld in enumerate(lines_data, start=10):
            line_vals_list.append({
                'statement_id': statement.id,
                'sequence': seq,
                'date': ld['date'],
                'reference': ld.get('reference', ''),
                'description': ld.get('description', ''),
                'amount': ld['amount'],
                'balance': ld.get('balance', 0.0),
            })
        self.env['co.bank.statement.line'].create(line_vals_list)

        statement.message_post(
            body=_('Imported %d lines from file: %s') % (
                len(line_vals_list), self.filename or 'unknown',
            ),
        )

        # Auto-reconcile if requested
        if self.auto_reconcile:
            statement.action_auto_reconcile()

        # Return the created statement
        return {
            'type': 'ir.actions.act_window',
            'name': _('Bank Statement'),
            'res_model': 'co.bank.statement.import',
            'res_id': statement.id,
            'view_mode': 'form',
            'target': 'current',
        }

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _decode_file(raw_bytes, encoding):
        """Decode bytes trying the configured encoding first, then fallbacks."""
        encodings = [encoding, 'utf-8', 'latin-1', 'cp1252']
        # Deduplicate while keeping order
        seen = set()
        unique = []
        for enc in encodings:
            if enc not in seen:
                seen.add(enc)
                unique.append(enc)

        for enc in unique:
            try:
                return raw_bytes.decode(enc)
            except (UnicodeDecodeError, LookupError):
                continue
        raise UserError(
            _('Could not decode the file. Tried encodings: %s') % ', '.join(unique)
        )

    def _parse_csv(self, content, fmt):
        """Parse CSV content according to the bank format configuration.

        Returns a list of dicts: [{date, reference, description, amount, balance}, ...]
        """
        delimiter = fmt.get_delimiter_char()
        lines = content.splitlines()

        # Strip BOM if present
        if lines and lines[0].startswith('\ufeff'):
            lines[0] = lines[0][1:]

        # Skip header and footer
        skip_top = fmt.skip_header_lines
        skip_bottom = fmt.skip_footer_lines
        if skip_bottom > 0:
            data_lines = lines[skip_top:-skip_bottom] if skip_bottom else lines[skip_top:]
        else:
            data_lines = lines[skip_top:]

        # Filter out blank lines
        data_lines = [l for l in data_lines if l.strip()]

        result = []
        reader = csv.reader(data_lines, delimiter=delimiter)
        for row_num, row in enumerate(reader, start=skip_top + 1):
            try:
                parsed = self._parse_row(row, fmt, row_num)
                if parsed:
                    result.append(parsed)
            except Exception as e:
                _logger.warning('Row %d skipped: %s — %s', row_num, row, e)
                continue

        return result

    def _parse_row(self, row, fmt, row_num):
        """Parse a single CSV row into a dict."""
        # Need at least enough columns for date + amount
        min_cols = max(
            fmt.col_date,
            fmt.col_debit if fmt.col_debit >= 0 else 0,
            fmt.col_credit if fmt.col_credit >= 0 else 0,
            fmt.col_amount if fmt.col_amount >= 0 else 0,
        ) + 1
        if len(row) < min_cols:
            return None

        # Date
        date_str = row[fmt.col_date].strip()
        if not date_str:
            return None
        date_val = self._parse_date(date_str, fmt.date_format)
        if not date_val:
            return None

        # Reference
        reference = ''
        if 0 <= fmt.col_reference < len(row):
            reference = row[fmt.col_reference].strip()

        # Description
        description = ''
        if 0 <= fmt.col_description < len(row):
            description = row[fmt.col_description].strip()

        # Amount — either from debit/credit columns or single amount column
        if fmt.col_amount >= 0 and fmt.col_amount < len(row):
            amount = fmt.parse_number(row[fmt.col_amount])
        else:
            debit = 0.0
            credit = 0.0
            if 0 <= fmt.col_debit < len(row):
                debit = fmt.parse_number(row[fmt.col_debit])
            if 0 <= fmt.col_credit < len(row):
                credit = fmt.parse_number(row[fmt.col_credit])
            # In bank statement: credit = money in, debit = money out
            amount = credit - debit

        # Balance
        balance = 0.0
        if 0 <= fmt.col_balance < len(row):
            balance = fmt.parse_number(row[fmt.col_balance])

        return {
            'date': date_val,
            'reference': reference,
            'description': description,
            'amount': amount,
            'balance': balance,
        }

    @staticmethod
    def _parse_date(date_str, date_format):
        """Parse a date string, trying the configured format first then common alternatives."""
        formats = [date_format, '%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y', '%Y%m%d', '%m/%d/%Y']
        seen = set()
        unique = []
        for f in formats:
            if f not in seen:
                seen.add(f)
                unique.append(f)

        for f in unique:
            try:
                return datetime.strptime(date_str.strip(), f).date()
            except ValueError:
                continue
        _logger.warning('Could not parse date: %r', date_str)
        return None
