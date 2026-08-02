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


from odoo import api, fields, models, _, Command, SUPERUSER_ID
from odoo.osv.expression import AND, OR

from operator import itemgetter
from re import findall as regex_findall

from odoo.osv import expression
from collections import defaultdict
from odoo.exceptions import UserError, ValidationError

from dateutil.relativedelta import relativedelta
import json
from datetime import datetime, time
import math
import re

from ast import literal_eval

from odoo.addons.web.controllers.utils import clean_action
from odoo.tools import float_compare, float_round, float_is_zero, format_datetime, groupby
from odoo.tools.misc import OrderedSet, clean_context, format_date, groupby as tools_groupby


class StockPicking(models.Model):
    _inherit = 'stock.picking'
    
    sent_to_kit_qty_move = fields.Boolean("Picking Sent To Picking KIT Products",default=False,copy=False)

    bom_products_line_ids = fields.One2many('bom.products.stock.move', 'picking_id', string="Picking KIT Products", copy=False, auto_join=True)

    def mass_add_to_kit_product_qty(self):
        self.filtered(lambda picking: picking.state != 'cancel'   and picking.has_kits != False).add_to_kit_product_qty()
        return True

    def action_confirm(self):
        res = super().action_confirm()
        for picking in self.with_user(SUPERUSER_ID):
            if picking.has_kits:
                repeatedbom = picking.move_ids.bom_line_id.bom_id
                boms = set(repeatedbom)
                kit_products_lines = [fields.Command.clear()]
                for bom in boms:
                    kit_products_lines += [fields.Command.create({
                        'bom_id':bom.id,
                        'date': picking.date_done or picking.scheduled_date,
                        'picking_id': picking.id,
                    })]
                    picking.bom_products_line_ids._compute_kit_qty_requested()
                picking.bom_products_line_ids = kit_products_lines
        return res

    def _action_done(self):
        res = super()._action_done()
        for picking in self.with_user(SUPERUSER_ID):
            if picking.has_kits:
                repeatedbom = picking.move_ids.bom_line_id.bom_id
                boms = set(repeatedbom)
                kit_products_lines = [fields.Command.clear()]
                for bom in boms:
                    kit_products_lines += [fields.Command.create({
                        'bom_id':bom.id,
                        'date': picking.date_done or picking.scheduled_date,
                        'picking_id': picking.id,
                    })]
                    picking.bom_products_line_ids.action_copute_kit_qty()
                    picking.update({'sent_to_kit_qty_move': True})
                picking.bom_products_line_ids = kit_products_lines
        return res

    def add_to_kit_product_qty(self):
        for picking in self.with_user(SUPERUSER_ID):
            if picking.has_kits   and picking.state !='cancel':
                repeatedbom = picking.move_ids.bom_line_id.bom_id
                boms = set(repeatedbom)
                kit_products_lines = [fields.Command.clear()]
                for bom in boms:
                    kit_products_lines += [fields.Command.create({
                        'bom_id':bom.id,
                        'date': picking.date_done or picking.scheduled_date,
                        'picking_id': picking.id,
                    })]
                    picking.bom_products_line_ids.action_copute_kit_qty()
                    picking.update({'sent_to_kit_qty_move': True})
                picking.bom_products_line_ids = kit_products_lines


class BomProductsStockMove(models.Model):
    _name = 'bom.products.stock.move'
    _order = 'product_id, id'
    _description = 'Picking KIT Products'
    _rec_name ='product_id'
    _check_company_auto = True


    sequence = fields.Integer('Sequence', default=10)
    bom_id = fields.Many2one(
        'mrp.bom', 'BOM',
        index=True, ondelete='cascade')
    reference = fields.Char(string="Reference",compute='_compute_reference', store=True)
    product_tmpl_id = fields.Many2one(
        comodel_name='product.template',related='bom_id.product_tmpl_id',store=True,
        string="Product Template")
    product_id = fields.Many2one(
        'product.product', 'Product',
        compute='_compute_product_id', store=True, precompute=True,
        readonly=False,  check_company=True)
    product_uom = fields.Many2one(
        comodel_name='uom.uom',
        string="UOM",related='bom_id.product_uom_id',store=True)

    company_id = fields.Many2one('res.company', string='Company',index=True,related='picking_id.company_id',store=True)
    picking_id = fields.Many2one('stock.picking', 'Transfer', index=True, check_company=True,ondelete='cascade')

    user_id = fields.Many2one(
        'res.users', 'Responsible', related='picking_id.user_id',store=True)
    picking_type_id = fields.Many2one('stock.picking.type', 'Operation Type',related='picking_id.picking_type_id',store=True)
    origin = fields.Char(string="Source Document", index='trigram',related='picking_id.origin',store=True)
    state = fields.Selection(
        related='picking_id.state',
        string="Picking Status",
        copy=False, store=True, precompute=True)
    date = fields.Datetime(string="Picking Date")
    stock_move_ids = fields.Many2many(
        comodel_name='stock.move',
        string="Stock Moves",
        compute='_compute_stock_move_ids', store=True, readonly=True, precompute=True,
        check_company=True,ondelete='cascade')

    @api.depends('picking_id', 'picking_id.move_ids.kit_product_tmpl_id')
    def _compute_stock_move_ids(self):
        for line in self:
            move_ids = self.env['stock.move'].search([('picking_id', '=', line.picking_id.id),('kit_product_tmpl_id', '=', line.product_tmpl_id.id),('company_id', '=', line.company_id.id)])
            if move_ids:
                line.stock_move_ids = move_ids.ids

    kit_qty_delivered = fields.Float(
        string="Delivered",
        compute='_compute_kit_qty_delivered',
        digits='Product Unit of Measure',
        store=True,  copy=False, precompute=True)
    kit_qty_requested = fields.Float(
        string="Ordered",
        compute='_compute_kit_qty_requested',
        digits='Product Unit of Measure',
        store=True,  copy=False, precompute=True)
    qty_deviation = fields.Float(
        'QTY Deviation',
        digits='Product Unit of Measure',compute='_compute_qty_deviation',store=True)

    standard_price = fields.Float(
        'Cost', company_dependent=True,
        digits='Product Price',copy=False)
    qty_delivered_total_cost = fields.Float(compute='_compute_qty_delivered_total_cost', store=True,string='Delivered SubTotal')
    qty_requested_total_cost = fields.Float(compute='_compute_qty_requested_total_cost', store=True,string='Requested SubTotal')
    qty_deviation_total_cost = fields.Float(compute='_compute_qty_deviation_total_cost', store=True,string='Deviation SubTotal')

    @api.depends('kit_qty_delivered', 'standard_price')
    def _compute_qty_delivered_total_cost(self):
        for rec in self:
            rec.qty_delivered_total_cost = rec.kit_qty_delivered * rec.standard_price

    @api.depends('kit_qty_requested', 'standard_price')
    def _compute_qty_requested_total_cost(self):
        for rec in self:
            rec.qty_requested_total_cost = rec.kit_qty_requested * rec.standard_price

    @api.depends('qty_deviation', 'standard_price')
    def _compute_qty_deviation_total_cost(self):
        for rec in self:
            rec.qty_deviation_total_cost = rec.qty_deviation * rec.standard_price



    def button_bom_cost(self):
        self.ensure_one()
        self._set_price_from_bom()

    def action_bom_cost(self):
        for product in self:
            boms_to_recompute = product.bom_id
            product._set_price_from_bom(boms_to_recompute)

    def _set_price_from_bom(self, boms_to_recompute=False):
        self.ensure_one()
        bom = self.bom_id
        if bom:
            self.standard_price = self._compute_bom_price(bom, boms_to_recompute=boms_to_recompute)
        else:
            bom = self.env['mrp.bom'].search([('byproduct_ids.product_id', '=', self.product_id.id)], order='sequence, product_id, id', limit=1)
            if bom:
                price = self._compute_bom_price(bom, boms_to_recompute=boms_to_recompute, byproduct_bom=True)
                if price:
                    self.standard_price = price

    def _compute_bom_price(self, bom, boms_to_recompute=False, byproduct_bom=False):
        self.ensure_one()
        if not bom:
            return 0
        if not boms_to_recompute:
            boms_to_recompute = []
        total = 0

        for line in bom.bom_line_ids:
            if line.child_bom_id and line.child_bom_id in boms_to_recompute:
                child_total = line.product_id._compute_bom_price(line.child_bom_id, boms_to_recompute=boms_to_recompute)
                total += line.product_id.uom_id._compute_price(child_total, line.product_uom_id) * line.product_qty
            else:
                total += line.product_id.uom_id._compute_price(line.product_id.standard_price, line.product_uom_id) * line.product_qty
        if byproduct_bom:
            byproduct_lines = bom.byproduct_ids.filtered(lambda b: b.product_id == self and b.cost_share != 0)
            product_uom_qty = 0
            for line in byproduct_lines:
                product_uom_qty += line.product_uom_id._compute_quantity(line.product_qty, self.product_uom, round=False)
            byproduct_cost_share = sum(byproduct_lines.mapped('cost_share'))
            if byproduct_cost_share and product_uom_qty:
                return total * byproduct_cost_share / 100 / product_uom_qty
        else:
            byproduct_cost_share = sum(bom.byproduct_ids.mapped('cost_share'))
            if byproduct_cost_share:
                total *= float_round(1 - byproduct_cost_share / 100, precision_rounding=0.0001)
            return bom.product_uom_id._compute_price(total / bom.product_qty, self.product_uom)



    @api.depends('kit_qty_delivered','kit_qty_requested')
    def _compute_qty_deviation(self):
        for bom in self:
            bom.qty_deviation = bom.kit_qty_delivered - bom.kit_qty_requested
            

    @api.depends('bom_id','picking_id','picking_id.move_ids','product_id','product_uom','company_id')
    def _compute_kit_qty_requested(self):
        for order_line in self:
            boms = order_line.bom_id
            dropship = any(m._is_dropshipped() for m in order_line.picking_id.move_ids)
            if not boms and dropship:
                boms = boms._bom_find(order_line.product_id, company_id=order_line.company_id.id, bom_type='phantom')[order_line.product_id]
            relevant_bom = boms.filtered(lambda b: b.type == 'phantom')
            if relevant_bom:
                if dropship:
                    moves = order_line.picking_id.move_ids.filtered(lambda m: m.state != 'cancel')
                    if any((m.location_dest_id.usage == 'customer' and m.state not in ('cancel'))
                           or (m.location_dest_id.usage != 'customer'
                           and m.state not in ('cancel')
                           and float_compare(m.product_uom_qty,
                                             sum(sub_m.product_uom._compute_quantity(sub_m.product_uom_qty, m.product_uom) for sub_m in m.returned_move_ids if sub_m.state not in ('cancel')),
                                             precision_rounding=m.product_uom.rounding) > 0)
                           for m in moves) or not moves:
                        order_line.qty_requested = 0
                    else:
                        order_line.qty_requested = 0
                    continue
                moves = order_line.picking_id.move_ids.filtered(lambda m: m.state not in ('cancel') and not m.scrapped)
                filters = {
                    'incoming_moves': lambda m: m.location_dest_id.usage == 'customer' and (not m.origin_returned_move_id or (m.origin_returned_move_id and m.to_refund)),
                    'outgoing_moves': lambda m: m.location_dest_id.usage != 'customer' and m.to_refund
                }
                order_qty = 1
                qty_requested = moves._compute_kit_quantities(order_line.product_id, order_qty, relevant_bom, filters)
                order_line.kit_qty_requested = relevant_bom.product_uom_id._compute_quantity(qty_requested, order_line.product_uom)
                order_line._set_price_from_bom()

    @api.depends('bom_id')
    def _compute_product_id(self):
        for kit in self:
            bom = kit.bom_id
            if bom and (
                not kit.product_id or bom.product_tmpl_id != kit.product_tmpl_id
                or bom.product_id and bom.product_id != kit.product_id
            ):
                kit.product_id = bom.product_id or bom.product_tmpl_id.product_variant_id

    @api.depends('bom_id', 'bom_id.code','bom_id.product_tmpl_id')
    def _compute_reference(self):
        for move in self:
            if move.bom_id:
                if move.bom_id.code:
                    move.reference = move.bom_id.code
                else:
                    move.reference = move.bom_id.product_tmpl_id.name

    def action_copute_kit_qty(self):
        for move in self:
            move._compute_kit_qty_requested()
            move._compute_kit_qty_delivered()

    @api.depends('bom_id','picking_id','picking_id.move_ids','product_id','product_uom','company_id')
    def _compute_kit_qty_delivered(self):
        for order_line in self:
            boms = order_line.bom_id
            dropship = any(m._is_dropshipped() for m in order_line.picking_id.move_ids)
            if not boms and dropship:
                boms = boms._bom_find(order_line.product_id, company_id=order_line.company_id.id, bom_type='phantom')[order_line.product_id]
            relevant_bom = boms.filtered(lambda b: b.type == 'phantom')
            if relevant_bom:
                if dropship:
                    moves = order_line.picking_id.move_ids.filtered(lambda m: m.state != 'cancel')
                    if any((m.location_dest_id.usage == 'customer' and m.state != 'done')
                           or (m.location_dest_id.usage != 'customer'
                           and m.state == 'done'
                           and float_compare(m.quantity,
                                             sum(sub_m.product_uom._compute_quantity(sub_m.quantity, m.product_uom) for sub_m in m.returned_move_ids if sub_m.state == 'done'),
                                             precision_rounding=m.product_uom.rounding) > 0)
                           for m in moves) or not moves:
                        order_line.qty_delivered = 0
                    else:
                        order_line.qty_delivered = 0
                    continue
                moves = order_line.picking_id.move_ids.filtered(lambda m: m.state == 'done' and not m.scrapped)
                filters = {
                    'incoming_moves': lambda m: m.location_dest_id.usage == 'customer' and (not m.origin_returned_move_id or (m.origin_returned_move_id and m.to_refund)),
                    'outgoing_moves': lambda m: m.location_dest_id.usage != 'customer' and m.to_refund
                }
                order_qty = 1
                qty_delivered = moves._compute_kit_quantities(order_line.product_id, order_qty, relevant_bom, filters)
                order_line.kit_qty_delivered = relevant_bom.product_uom_id._compute_quantity(qty_delivered, order_line.product_uom)
                order_line._set_price_from_bom()



class StockMove(models.Model):
    _inherit = 'stock.move'


    kit_product_tmpl_id = fields.Many2one('product.template', 'Finished Product Template', related='bom_line_id.bom_id.product_tmpl_id',store=True)
    kit_product_id = fields.Many2one(
        'product.product', 'Finished Product',
        compute='_compute_product_id', store=True, precompute=True,
        readonly=False,  check_company=True)

    @api.depends('bom_line_id.bom_id')
    def _compute_product_id(self):
        for kit in self:
            bom = kit.bom_line_id.bom_id
            if bom and (
                not kit.product_id or bom.product_tmpl_id != kit.product_tmpl_id
                or bom.product_id and bom.product_id != kit.product_id
            ):
                kit.kit_product_id = bom.product_id or bom.product_tmpl_id.product_variant_id

    # def _prepare_account_move_line(self, qty, cost, credit_account_id, debit_account_id, svl_id, description):
    #     self.ensure_one()
    #     debit_value = self.company_id.currency_id.round(cost)
    #     credit_value = debit_value
    #     for move in self:
    #         if move.kit_product_tmpl_id:
    #             product_accounts = move.kit_product_tmpl_id.get_product_accounts()
    #             if move.picking_type_id.code == 'outgoing' and cost > 0:
    #                 debit_account_id = product_accounts['stock_output'].id
    #             if move.picking_type_id.code == 'incoming' and cost > 0:
    #                 credit_account_id = product_accounts['stock_output'].id
    #     valuation_partner_id = self._get_partner_id_for_valuation_lines()
    #     res = [(0, 0, line_vals) for line_vals in self._generate_valuation_lines_data(valuation_partner_id, qty, debit_value, credit_value, debit_account_id, credit_account_id, svl_id, description).values()]

    #     return res

   
    def _prepare_account_move_line(self, qty, cost, credit_account_id, debit_account_id, svl_id, description):
        res = super(StockMove, self)._prepare_account_move_line(qty, cost, credit_account_id, debit_account_id, svl_id, description)
        debit_value = self.company_id.currency_id.round(cost)
        credit_value = debit_value
        valuation_partner_id = self._get_partner_id_for_valuation_lines()
        for move in self:
            if move.kit_product_tmpl_id:
                product_accounts = move.kit_product_tmpl_id.get_product_accounts()
                if move.picking_type_id.code == 'outgoing' and cost > 0:
                    debit_account_id = product_accounts['stock_output'].id
                if move.picking_type_id.code == 'incoming' and cost > 0:
                    credit_account_id = product_accounts['stock_output'].id

            res = [(0, 0, line_vals) for line_vals in self._generate_valuation_lines_data(valuation_partner_id,qty, debit_value, credit_value, debit_account_id, credit_account_id, svl_id, description).values()]

        return res
