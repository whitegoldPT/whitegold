from odoo import fields, models

class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    transit_location_id = fields.Many2one(
        "stock.location",
        string="Internal Consumption Transit Location",
        domain="[('usage', '=', 'transit')]",
        config_parameter="internal_consumption_flow.transit_location_id",
        help="The intermediate location for 2-step consumption flow."
    )
    consumption_location_id = fields.Many2one(
        "stock.location",
        string="Internal Consumption Virtual Location",
        config_parameter="internal_consumption_flow.consumption_location_id",
        help="The final virtual location where goods are considered consumed/expensed."
    )
