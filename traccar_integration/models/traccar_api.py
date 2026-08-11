import requests
import json
import urllib3
from datetime import datetime, timedelta
from odoo import models, fields, api
from odoo.exceptions import UserError
import logging
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT

# Silence insecure request warnings (self-signed certificates)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_logger = logging.getLogger(__name__)


class TraccarAPI(models.TransientModel):
    _name = 'traccar.api'
    _description = 'Traccar API Interface'

    config_id = fields.Many2one('traccar.config', string='Configuration', required=True)

    def _get_auth(self):
        """Get authentication tuple"""
        return (self.config_id.username, self.config_id.password)

    def _make_request(self, endpoint, method='GET', data=None, params=None):
        """Make API request to Traccar server"""
        url = f"{self.config_id.server_url.rstrip('/')}/api/{endpoint.lstrip('/')}"

        try:
            response = requests.request(
                method,
                url,
                auth=self._get_auth(),
                json=data,
                params=params,
                timeout=15,
                verify=False  # Disable for testing, enable in production
            )
            response.raise_for_status()
            return response.json() if response.content else []

        except requests.exceptions.RequestException as e:
            _logger.error(f"Traccar API request failed: {str(e)}")
            raise UserError(f"Failed to communicate with Traccar server: {str(e)}")

    def _parse_traccar_datetime(self, dt_str):
        """Convert Traccar datetime string to Odoo format"""
        if not dt_str:
            return False

        try:
            # Parse ISO format with timezone
            dt = datetime.strptime(dt_str, "%Y-%m-%dT%H:%M:%S.%f%z")
            # Convert to naive datetime in UTC
            dt_utc = dt.astimezone(tz=None).replace(tzinfo=None)
            return dt_utc.strftime(DEFAULT_SERVER_DATETIME_FORMAT)
        except ValueError:
            try:
                # Fallback for different format
                dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
                return dt.strftime(DEFAULT_SERVER_DATETIME_FORMAT)
            except Exception:
                _logger.warning(f"Failed to parse datetime: {dt_str}")
                return False

    def sync_devices(self):
        """Synchronize existing devices from Traccar"""
        # Get existing devices to know what to sync
        existing_devices = self.env['traccar.device'].search([])
        if not existing_devices:
            _logger.info("No devices registered in Odoo for synchronization.")
            return

        # Fetch only the specific devices we have in Odoo if they have a traccar_id
        traccar_ids = existing_devices.filtered(lambda d: d.traccar_id).mapped('traccar_id')
        params = {'id': traccar_ids} if traccar_ids else {}

        # If some devices don't have traccar_id yet (perhaps manually created with unique_id)
        # we still fetch all and filter by unique_id to link them
        devices_data = self._make_request('devices', params=params)

        existing_unique_ids = set(existing_devices.mapped('unique_id'))
        existing_traccar_ids = set(existing_devices.mapped('traccar_id'))

        updated_count = 0
        for device_data in devices_data:
            tr_id = device_data['id']
            un_id = device_data.get('uniqueId')

            # Check if this device is wanted in Odoo
            if tr_id in existing_traccar_ids or un_id in existing_unique_ids:
                device = existing_devices.filtered(lambda d: d.traccar_id == tr_id or d.unique_id == un_id)[:1]
                
                vals = {
                    'traccar_id': tr_id,
                    'name': device_data.get('name', ''),
                    'unique_id': un_id,
                    'status': device_data.get('status', 'unknown'),
                    'last_update': self._parse_traccar_datetime(device_data.get('lastUpdate')),
                    'group_id': device_data.get('groupId'),
                    'phone': device_data.get('phone', ''),
                    'model': device_data.get('model', ''),
                    'contact': device_data.get('contact', ''),
                    'category': device_data.get('category'),
                    'disabled': device_data.get('disabled', False),
                    'attributes': json.dumps(device_data.get('attributes', {})),
                }

                if device:
                    device.write(vals)
                else:
                    self.env['traccar.device'].create(vals)
                updated_count += 1

        _logger.info(f"Updated {updated_count} existing devices from Traccar")


    def sync_positions(self, device_id=None, from_date=None, to_date=None):
        """Synchronize positions from Traccar for existing devices only"""
        if not from_date:
            from_date = datetime.now() - timedelta(days=1)
        if not to_date:
            to_date = fields.Datetime.now()

        # Get existing traccar_ids from Odoo to restrict synchronization
        if device_id:
            # If a specific ID is passed (e.g. from a tool or cron), we check it exists in Odoo
            target_devices = self.env['traccar.device'].search([('traccar_id', '=', device_id)])
        else:
            target_devices = self.env['traccar.device'].search([('traccar_id', '!=', False)])

        traccar_ids = target_devices.mapped('traccar_id')

        if not traccar_ids:
            _logger.info("No devices with Traccar IDs found in Odoo for position synchronization.")
            return

        params = {
            'from': from_date.isoformat() + 'Z',
            'to': to_date.isoformat() + 'Z',
            'deviceId': traccar_ids
        }

        _logger.info(f"Fetching positions from {params['from']} to {params['to']} for {len(traccar_ids)} devices")
        
        # Positions endpoint can return a lot of data; by passing explicit deviceIds,
        # we ensure we ONLY get what we want and the server doesn't overwork.
        positions_data = self._make_request('positions', params=params)

        created_count = 0
        for position_data in positions_data:
            existing = self.env['traccar.position'].search([
                ('traccar_id', '=', position_data['id'])
            ])

            if not existing:
                device = target_devices.filtered(lambda d: d.traccar_id == position_data['deviceId'])[:1]
                if device:
                    vals = {
                        'traccar_id': position_data['id'],
                        'device_id': device.id,
                        'protocol': position_data.get('protocol'),
                        'device_time': self._parse_traccar_datetime(position_data.get('deviceTime')),
                        'fix_time': self._parse_traccar_datetime(position_data.get('fixTime')),
                        'server_time': self._parse_traccar_datetime(position_data.get('serverTime')),
                        'outdated': position_data.get('outdated', False),
                        'valid': position_data.get('valid', True),
                        'latitude': position_data.get('latitude', 0),
                        'longitude': position_data.get('longitude', 0),
                        'altitude': position_data.get('altitude'),
                        'speed': position_data.get('speed'),
                        'course': position_data.get('course'),
                        'accuracy': position_data.get('accuracy'),
                        'attributes': json.dumps(position_data.get('attributes', {})),
                    }
                    self.env['traccar.position'].create(vals)
                    created_count += 1

        _logger.info(f"Created {created_count} new positions for {len(traccar_ids)} devices from Traccar")

        # After positions are synced, trigger update of computed fields on devices
        # (battery, fuel, odometer, etc.)
        if created_count > 0:
            target_devices.update_computed_fields()


    def send_command(self, device_id, command_type, attributes=None):
        """Send command to device"""
        data = {
            'deviceId': device_id,
            'type': command_type,
            'attributes': attributes or {}
        }

        return self._make_request('commands/send', method='POST', data=data)