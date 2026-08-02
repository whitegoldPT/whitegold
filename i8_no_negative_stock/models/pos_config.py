# -*- coding: utf-8 -*-
from odoo import api, fields, models

class PosConfig(models.Model):
    _inherit = "pos.config"

    block_out_of_stock = fields.Boolean(
        string="Block Out-of-Stock Products",
        default = True,
        help="If enabled, the POS will prevent validating orders when any storable product line "
             "exceeds available stock in the configured stock location/warehouse."
    )
    block_use_forecast = fields.Boolean(
        string="Use Forecasted Qty (virtual)",
        default=False,
        help="If enabled, compare against forecasted (virtual) quantity instead of on-hand/free quantity."
    )
    block_ignore_consumables = fields.Boolean(
        string="Ignore Consumables",
        default=False,
        help="If enabled, consumable products won't be checked."
    )
    low_stock_alert_enabled = fields.Boolean(
        "Low-stock toast alert",
        default=True,
        help="Show a toast when items in the current order are near out-of-stock."
    )
    low_stock_threshold = fields.Integer(
        "Low-stock threshold",
        default=15,
        help="Show a warning when (available - qty in this order) <= threshold."
    )
    low_stock_email_recipients = fields.Char(
        "Low-stock email recipients (comma-separated)",
        help="Comma-separated email addresses. If set, a one-time email is sent when a product first drops to/below the threshold."
    )
