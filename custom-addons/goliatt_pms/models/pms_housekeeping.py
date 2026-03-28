from odoo import api, fields, models, _
from odoo.exceptions import UserError


class PmsHousekeepingTask(models.Model):
    _name = 'pms.housekeeping.task'
    _description = 'Housekeeping Task'
    _inherit = ['mail.thread']
    _order = 'date desc, priority desc, name desc'

    name = fields.Char(
        string='Task No.',
        readonly=True,
        copy=False,
        index=True,
        default=lambda self: _('New'),
    )
    room_id = fields.Many2one(
        'pms.room',
        required=True,
        string='Room',
    )
    property_id = fields.Many2one(
        'pms.property',
        related='room_id.property_id',
        string='Property',
        store=True,
    )
    date = fields.Date(
        default=fields.Date.context_today,
        string='Date',
    )
    task_type = fields.Selection(
        [
            ('checkout_clean', 'Check-out Clean'),
            ('stayover', 'Stayover'),
            ('deep_clean', 'Deep Clean'),
            ('turndown', 'Turndown'),
            ('inspection', 'Inspection'),
        ],
        string='Task Type',
        default='stayover',
    )
    attendant_id = fields.Many2one(
        'hr.employee',
        string='Attendant',
    )
    supervisor_id = fields.Many2one(
        'hr.employee',
        string='Supervisor',
    )
    state = fields.Selection(
        [
            ('pending', 'Pending'),
            ('in_progress', 'In Progress'),
            ('completed', 'Completed'),
            ('inspected', 'Inspected'),
            ('failed', 'Failed'),
        ],
        default='pending',
        string='State',
        tracking=True,
    )
    priority = fields.Selection(
        [
            ('normal', 'Normal'),
            ('rush', 'Rush'),
            ('vip', 'VIP'),
        ],
        default='normal',
        string='Priority',
    )
    start_time = fields.Datetime(string='Start Time')
    end_time = fields.Datetime(string='End Time')
    duration_minutes = fields.Float(
        compute='_compute_duration',
        string='Duration (min)',
    )
    notes = fields.Text(string='Notes')
    inspection_notes = fields.Text(string='Inspection Notes')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'pms.housekeeping.task'
                ) or _('New')
        return super().create(vals_list)

    @api.depends('start_time', 'end_time')
    def _compute_duration(self):
        for task in self:
            if task.start_time and task.end_time:
                delta = task.end_time - task.start_time
                task.duration_minutes = delta.total_seconds() / 60.0
            else:
                task.duration_minutes = 0.0

    def action_start(self):
        for task in self:
            task.state = 'in_progress'
            task.start_time = fields.Datetime.now()
            task.room_id.housekeeping_status = 'cleaning'

    def action_complete(self):
        for task in self:
            if task.state != 'in_progress':
                raise UserError(_('Task must be in progress to complete.'))
            task.state = 'completed'
            task.end_time = fields.Datetime.now()
            task.room_id.housekeeping_status = 'clean'

    def action_inspect(self):
        for task in self:
            if task.state != 'completed':
                raise UserError(_('Task must be completed to inspect.'))
            task.state = 'inspected'
            task.room_id.housekeeping_status = 'inspected'

    def action_fail(self):
        for task in self:
            task.state = 'failed'
            task.room_id.housekeeping_status = 'dirty'
