from odoo import api, fields, models
from odoo.exceptions import ValidationError


class CoSalaryConcept(models.Model):
    """Configurable salary concepts with formulas.

    Formula variables available during evaluation:
        basic_salary, transport_allowance, smlmv, uvt, worked_days,
        total_days, overtime_amount, commissions, bonuses,
        ibc (ingreso base de cotizacion)
    """
    _name = 'co.salary.concept'
    _description = 'Salary Concept'
    _order = 'sequence, code'

    name = fields.Char(string='Name', required=True, translate=True)
    code = fields.Char(string='Code', required=True)
    sequence = fields.Integer(string='Sequence', default=10)
    concept_type = fields.Selection([
        ('earning', 'Earning (Devengado)'),
        ('deduction', 'Deduction (Deducción)'),
        ('employer', 'Employer Contribution (Aporte Empleador)'),
        ('provision', 'Provision (Provisión)'),
    ], string='Type', required=True)
    formula = fields.Text(
        string='Formula',
        help='Python expression. Available vars: basic_salary, transport_allowance, '
             'smlmv, uvt, worked_days, total_days, overtime_amount, commissions, '
             'bonuses, ibc',
    )
    active = fields.Boolean(default=True)
    appears_on_payslip = fields.Boolean(
        string='Appears on Payslip', default=True,
    )
    notes = fields.Text(string='Notes')

    _sql_constraints = [
        ('code_unique', 'UNIQUE(code)', 'Concept code must be unique.'),
    ]

    @api.constrains('formula')
    def _check_formula(self):
        """Validate that the formula is syntactically correct."""
        for rec in self:
            if rec.formula:
                try:
                    compile(rec.formula.strip(), '<salary_concept>', 'eval')
                except SyntaxError as e:
                    raise ValidationError(
                        f'Invalid formula for concept {rec.code}: {e}'
                    )

    def evaluate(self, variables):
        """Evaluate the formula with the given variables dict.

        Returns float result or 0.0 if formula is empty.
        """
        self.ensure_one()
        if not self.formula:
            return 0.0
        safe_vars = {
            'round': round,
            'min': min,
            'max': max,
            'abs': abs,
        }
        safe_vars.update(variables)
        try:
            result = eval(self.formula.strip(), {"__builtins__": {}}, safe_vars)
            return float(result) if result else 0.0
        except Exception:
            return 0.0
