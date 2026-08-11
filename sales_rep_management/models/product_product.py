# -*- coding: utf-8 -*-
from odoo import models, api


class ProductProduct(models.Model):
    _inherit = 'product.product'

    def _notify_sse(self, reason):
        try:
            from odoo.addons.sales_rep_management.controllers.sse import notify_all
            self.env.cr.postcommit.add(lambda: notify_all(reason=reason))
        except ImportError:
            pass

    @api.model_create_multi
    def create(self, vals_list):
        products = super(ProductProduct, self).create(vals_list)
        self._notify_sse('product_created')
        return products

    def write(self, vals):
        res = super(ProductProduct, self).write(vals)
        # Any change to products should trigger a sync
        self._notify_sse('product_updated')
        return res

    def unlink(self):
        res = super(ProductProduct, self).unlink()
        self._notify_sse('product_deleted')
        return res
