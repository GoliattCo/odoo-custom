from odoo import fields, models


class PmsChannel(models.Model):
    _name = 'pms.channel'
    _description = 'Distribution Channel'
    _order = 'name'

    name = fields.Char(required=True, string='Channel Name')
    channel_type = fields.Selection(
        [
            ('ota', 'OTA'),
            ('gds', 'GDS'),
            ('direct', 'Direct'),
            ('walk_in', 'Walk-in'),
            ('phone', 'Phone'),
        ],
        string='Type',
        default='ota',
    )
    commission_pct = fields.Float(string='Commission %')
    api_url = fields.Char(string='API URL')
    api_key = fields.Char(string='API Key')
    api_secret = fields.Char(string='API Secret')
    is_active = fields.Boolean(default=True, string='Active')
    notes = fields.Text(string='Notes')
