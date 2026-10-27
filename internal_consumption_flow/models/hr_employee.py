from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    destination_location_id = fields.Many2one(
        "stock.location",
        string="Consumption Location",
        help="The stock location where this employee consumes goods "
             "(e.g. 'Marketing Office Shelf').",
        domain="[('usage', '=', 'internal')]",
    )
