# -*- coding: utf-8 -*-
from odoo import fields, models

class I8LowStockFlag(models.Model):
    _name = "i8.low.stock.flag"
    _description = "POS Low Stock Email Flag"
    _rec_name = "product_id"
    _order = "id desc"

    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    config_id  = fields.Many2one("pos.config", required=True, ondelete="cascade")
    product_id = fields.Many2one("product.product", required=True, ondelete="cascade")
    location_id = fields.Many2one("stock.location", required=True, ondelete="cascade")
    last_remaining = fields.Float(digits="Product Unit of Measure")
    notified_at = fields.Datetime(default=fields.Datetime.now)
