# -*- coding: utf-8 -*-
import json
import time
import logging
import odoo.addons.decimal_precision as dp
from datetime import date, datetime
from dateutil import relativedelta
from odoo import fields, models
from odoo.tools import float_compare
from odoo.tools.translate import _
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT, DEFAULT_SERVER_DATE_FORMAT
from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


class stock_picking(models.Model):
    _inherit = "stock.picking"

    def do_internal_transfer_details(self):
        context = dict(self._context or {})
        picking = [picking]
        context.update({
            'active_model': self._name,
            'active_ids': picking,
            'active_id': len(picking) and picking[0] or False
        })

        return True

    def button_validate(self):
        res = super(stock_picking, self).button_validate()
        if self.transfer_id:
            # Refresh transit quantities when picking is done
            self.transfer_id._compute_transit_quantities()

        return res

    transfer_id = fields.Many2one('stock.internal.transfer', 'Transfer')
    send_picking = fields.Boolean()


class stock_move(models.Model):
    _inherit = "stock.move"

    analytic_account_id = fields.Many2one('account.analytic.account', 'Analytic Account')
    # ADD: Second UOM field for stock moves
    second_uom = fields.Integer(
        string='Second UOM',
        default=1,
        help="Second unit of measure for the product"
    )
    need_second_uom = fields.Boolean(
        string='Need Second UOM',
        compute='_compute_need_second_uom',
        store=True,
        help="Indicates if the product requires second UOM"
    )

    @api.depends('product_id')
    def _compute_need_second_uom(self):
        """Compute if product needs second UOM"""
        for move in self:
            if move.product_id:
                # Try to access need_second_uom on product, but handle gracefully if it doesn't exist
                try:
                    move.need_second_uom = move.product_id.need_second_uom
                except Exception:
                    # If field doesn't exist on product, default to False
                    move.need_second_uom = False
            else:
                move.need_second_uom = False


class stock_warehouse(models.Model):
    _inherit = "stock.warehouse"

    user_ids = fields.Many2many('res.users','company_user_rel','company_id','user_id','Owner user')
    spare_part_location=fields.Boolean()