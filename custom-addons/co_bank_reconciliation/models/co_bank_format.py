import logging

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class CoBankFormat(models.Model):
    _name = 'co.bank.format'
    _description = 'Colombian Bank File Format'
    _order = 'sequence, name'

    name = fields.Char(
        string='Format Name',
        required=True,
        translate=True,
    )
    code = fields.Char(
        string='Code',
        required=True,
        help='Internal code for this format (e.g. bancolombia_csv)',
    )
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)

    # --- File structure ---
    delimiter = fields.Selection(
        [
            ('comma', 'Comma (,)'),
            ('semicolon', 'Semicolon (;)'),
            ('tab', 'Tab'),
            ('pipe', 'Pipe (|)'),
        ],
        string='Delimiter',
        required=True,
        default='comma',
    )
    encoding = fields.Selection(
        [
            ('utf-8', 'UTF-8'),
            ('latin-1', 'Latin-1 (ISO 8859-1)'),
            ('cp1252', 'Windows CP1252'),
        ],
        string='File Encoding',
        required=True,
        default='utf-8',
    )
    skip_header_lines = fields.Integer(
        string='Header Lines to Skip',
        default=1,
        help='Number of lines at the top of the file to skip (e.g. column headers).',
    )
    skip_footer_lines = fields.Integer(
        string='Footer Lines to Skip',
        default=0,
        help='Number of lines at the bottom of the file to skip (e.g. totals row).',
    )
    date_format = fields.Char(
        string='Date Format',
        required=True,
        default='%d/%m/%Y',
        help='Python strftime format. Common: %d/%m/%Y, %Y-%m-%d, %Y%m%d',
    )

    # --- Column mapping (0-based indices) ---
    col_date = fields.Integer(string='Date Column', default=0)
    col_reference = fields.Integer(string='Reference Column', default=1)
    col_description = fields.Integer(string='Description Column', default=2)
    col_debit = fields.Integer(
        string='Debit Column',
        default=3,
        help='Set to -1 if not present (uses amount column instead).',
    )
    col_credit = fields.Integer(
        string='Credit Column',
        default=4,
        help='Set to -1 if not present (uses amount column instead).',
    )
    col_amount = fields.Integer(
        string='Amount Column',
        default=-1,
        help='Single amount column (positive=credit, negative=debit). '
             'Set to -1 if using separate debit/credit columns.',
    )
    col_balance = fields.Integer(
        string='Balance Column',
        default=5,
        help='Running balance column. Set to -1 if not present.',
    )

    # --- Number format ---
    thousands_separator = fields.Selection(
        [
            ('comma', 'Comma (1,000,000)'),
            ('dot', 'Dot (1.000.000)'),
            ('none', 'None'),
        ],
        string='Thousands Separator',
        default='comma',
        required=True,
    )
    decimal_separator = fields.Selection(
        [
            ('dot', 'Dot (1000.50)'),
            ('comma', 'Comma (1000,50)'),
        ],
        string='Decimal Separator',
        default='dot',
        required=True,
    )

    notes = fields.Text(string='Notes')

    _sql_constraints = [
        ('code_uniq', 'UNIQUE(code)', 'The format code must be unique.'),
    ]

    @api.constrains('col_debit', 'col_credit', 'col_amount')
    def _check_amount_columns(self):
        for rec in self:
            has_debit_credit = rec.col_debit >= 0 and rec.col_credit >= 0
            has_amount = rec.col_amount >= 0
            if not has_debit_credit and not has_amount:
                raise ValidationError(
                    _('You must configure either Debit/Credit columns or a single Amount column.')
                )

    def get_delimiter_char(self):
        """Return the actual delimiter character."""
        self.ensure_one()
        return {
            'comma': ',',
            'semicolon': ';',
            'tab': '\t',
            'pipe': '|',
        }[self.delimiter]

    def parse_number(self, value_str):
        """Parse a number string according to this format's number conventions.

        Colombian bank files commonly use:
          - dot as thousands separator, comma as decimal (1.234.567,89)
          - or comma as thousands, dot as decimal (1,234,567.89)
        """
        self.ensure_one()
        if not value_str:
            return 0.0
        s = value_str.strip().replace(' ', '')
        # Remove currency symbols / letters
        for ch in ('$', 'COP', 'cop'):
            s = s.replace(ch, '')
        s = s.strip()
        if not s or s == '-':
            return 0.0

        # Determine sign
        negative = False
        if s.startswith('(') and s.endswith(')'):
            negative = True
            s = s[1:-1]
        if s.startswith('-'):
            negative = True
            s = s[1:]

        # Remove thousands separator
        thou_char = {'comma': ',', 'dot': '.', 'none': ''}[self.thousands_separator]
        if thou_char:
            s = s.replace(thou_char, '')

        # Normalize decimal separator to dot
        dec_char = {'dot': '.', 'comma': ','}[self.decimal_separator]
        if dec_char == ',':
            s = s.replace(',', '.')

        try:
            val = float(s)
        except ValueError:
            _logger.warning('Could not parse number: %r', value_str)
            return 0.0
        return -val if negative else val
