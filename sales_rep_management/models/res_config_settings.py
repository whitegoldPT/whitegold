from odoo import models, fields, api

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    is_location_tracking_enabled = fields.Boolean(
        string="Enable Location Tracking",
        config_parameter='sales_rep_management.is_location_tracking_enabled',
        help="Enable tracking of sales representative locations during visits."
    )

    location_radius = fields.Float(
        string="Location Radius",
        config_parameter='sales_rep_management.location_radius',
        default=50.0,
        help="Default radius (in meters) around the customer location to consider a visit valid."
    )

    # Compatibility fields for Odoo 18 transition
    # These fields are required because stale views in the database (from Odoo 17)
    # may still reference them, causing Owl framework crashes if not defined.
    default_picking_policy = fields.Selection([
        ('direct', 'Deliver each product when available'),
        ('one', 'Deliver all products at once')
    ], string='Shipping Policy', default='direct', help='Compatibility field for un-migrated views')

    currency_provider = fields.Selection([
        ('ecb', 'European Central Bank'),
    ], string='Service', help='Compatibility field for un-migrated views', default='ecb')
    currency_interval_unit = fields.Selection([
        ('manually', 'Manually'),
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
    ], string='Interval Unit', help='Compatibility field for un-migrated views', default='manually')
    currency_next_execution_date = fields.Date(string='Next Execution Date', help='Compatibility field for un-migrated views', default=fields.Date.today())
