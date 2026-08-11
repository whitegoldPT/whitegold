# -*- coding: utf-8 -*-
#################################################################################
# Author      : Zero For Information Systems (<www.erpzero.com>)
# Copyright(c): 2016-Zero For Information Systems
# All Rights Reserved.
#
# This program is copyright property of the author mentioned above.
# You can`t redistribute it and/or modify it.
#
#################################################################################


from odoo import api, fields, models, _


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'


    @api.onchange('product_id')
    def _onchange_product_id_warning(self):
        res = super()._onchange_product_id_warning()
        if not self.product_id:
            return
        for line in self:
            if line.product_id.is_kits:
                line.product_id.action_bom_cost()
        return res
