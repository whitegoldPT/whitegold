from odoo import models, fields, api
from odoo.exceptions import ValidationError
import requests
import logging

_logger = logging.getLogger(__name__)

class TraccarConfig(models.Model):
    _name = 'traccar.config'
    _description = 'Traccar Server Configuration'
    _rec_name = 'server_url'

    server_url = fields.Char(
        string='Traccar Server URL',
        required=True,
        default='http://localhost:8082',
        help='URL of your Traccar server (e.g., http://your-server:8082)'
    )
    username = fields.Char(
        string='Username',
        required=True,
        help='Traccar username for API access'
    )
    password = fields.Char(
        string='Password',
        required=True,
        help='Traccar password for API access'
    )
    active = fields.Boolean(
        string='Active',
        default=True
    )
    last_sync = fields.Datetime(
        string='Last Synchronization',
        readonly=True
    )
    sync_interval = fields.Integer(
        string='Sync Interval (minutes)',
        default=2,
        help='Automatic synchronization interval in minutes'
    )
    browser_sync_interval = fields.Integer(
        string='Live Map Sync Interval (seconds)',
        default=10,
        help='How often the Live Map triggers an API sync from the browser'
    )

    @api.constrains('server_url')
    def _check_server_url(self):
        for record in self:
            if not record.server_url.startswith(('http://', 'https://')):
                raise ValidationError("Server URL must start with http:// or https://")

    def test_connection(self):
        """Test connection to Traccar server"""
        try:
            response = requests.get(
                f"{self.server_url}/api/server",
                auth=(self.username, self.password),
                timeout=10
            )
            if response.status_code == 200:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Success',
                        'message': 'Connection to Traccar server successful!',
                        'type': 'success',
                    }
                }
            else:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Error',
                        'message': f'Connection failed: {response.status_code}',
                        'type': 'danger',
                    }
                }
        except Exception as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Error',
                    'message': f'Connection failed: {str(e)}',
                    'type': 'danger',
                }
            }

    def sync_all_data(self):
        """Synchronize all data from Traccar"""
        api = self.env['traccar.api'].create({'config_id': self.id})
        api.sync_devices()
        api.sync_positions()
        self.last_sync = fields.Datetime.now()

    # ADD THIS METHOD FOR CRON JOB SUPPORT
    def cron_sync_all_data(self):
        """Method for cron job to sync all data"""
        for config in self.search([('active', '=', True)]):
            try:
                api = self.env['traccar.api'].create({'config_id': config.id})
                # sync_devices now only updates existing records
                api.sync_devices()
                
                # Sync positions for the last 24 hours (for existing devices only)
                from datetime import datetime, timedelta
                from_date = datetime.now() - timedelta(hours=24)
                api.sync_positions(from_date=from_date)
                
                config.last_sync = fields.Datetime.now()
                _logger.info("Cron sync completed for config: %s", config.server_url)
            except Exception as e:
                _logger.error("Cron sync failed for config %s: %s", config.server_url, str(e))

    @api.model
    def action_browser_sync(self):
        """Method called by browser to trigger a quick sync while watching the map"""
        config = self.search([('active', '=', True)], limit=1)
        if not config:
            return False

        # Throttling: only sync if last sync was more than the configured interval
        interval = config.browser_sync_interval or 30
        now = fields.Datetime.now()
        if config.last_sync and (now - config.last_sync).total_seconds() < interval:
            return False

        try:
            # Use FOR UPDATE NOWAIT to prevent multiple concurrent syncs from overlapping
            self.env.cr.execute('SELECT id FROM traccar_config WHERE id=%s FOR UPDATE NOWAIT', (config.id,))
            
            api = self.env['traccar.api'].create({'config_id': config.id})
            
            # 1. Sync device statuses (online/offline)
            api.sync_devices()
            
            # 2. Sync only recent positions for speed
            from datetime import datetime, timedelta
            from_date = datetime.now() - timedelta(minutes=5)
            api.sync_positions(from_date=from_date)
            
            config.last_sync = now
            return True
        except Exception as e:
            # psycopg2.errors.LockNotAvailable or similar if NOWAIT hits
            _logger.debug("Browser sync skipped or failed (likely concurrent update): %s", str(e))
            return False

    @api.model
    def get_browser_sync_interval(self):
        """Method for the browser to fetch its sync interval configuration"""
        config = self.search([('active', '=', True)], limit=1)
        return config.browser_sync_interval or 30