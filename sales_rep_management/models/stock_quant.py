# -*- coding: utf-8 -*-
import logging
from odoo import models, api

_logger = logging.getLogger(__name__)

class StockQuant(models.Model):
    _inherit = 'stock.quant'

    def _notify_product_update(self):
        try:
            from odoo.addons.sales_rep_management.controllers.sse import notify_all
            self.env.cr.postcommit.add(lambda: notify_all(reason='product_updated'))
        except Exception as e:
            _logger.error(f"Failed to register SSE for stock_quant update: {e}")

    @api.model_create_multi
    def create(self, vals_list):
        quants = super(StockQuant, self).create(vals_list)
        self._notify_product_update()
        return quants

    def write(self, vals):
        res = super(StockQuant, self).write(vals)
        # Only notify if quantity changes (optimization)
        if 'quantity' in vals or 'reserved_quantity' in vals or 'inventory_quantity' in vals:
            self._notify_product_update()
        return res

    def unlink(self):
        res = super(StockQuant, self).unlink()
        self._notify_product_update()
        return res
