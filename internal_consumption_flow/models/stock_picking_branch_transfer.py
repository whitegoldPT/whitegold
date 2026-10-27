# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
import logging

_logger = logging.getLogger(__name__)


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    inter_branch_request_id = fields.Many2one(
        'stock.inter.branch.request',
        string='Inter-Branch Request / طلب التحويل بين الفروع',
        readonly=True,
        copy=False,
        index=True
    )

    def _action_done(self):
        res = super()._action_done()
        for picking in self:
            if picking.inter_branch_request_id:
                req = picking.inter_branch_request_id
                is_return = getattr(req, 'request_type', 'transfer') == 'return'
                if picking == req.picking_out_id:
                    req.write({'state': 'in_transit'})
                    # Transfer actual valuation costs to incoming picking move_ids
                    if req.picking_in_id:
                        for out_move in picking.move_ids.filtered(lambda m: m.state == 'done'):
                            svls = out_move.sudo().stock_valuation_layer_ids
                            if svls:
                                qty = sum(svls.mapped('quantity'))
                                val = sum(svls.mapped('value'))
                                cost = abs(val / qty) if qty else 0.0
                            else:
                                cost = out_move.price_unit or out_move.product_id.with_company(out_move.company_id).standard_price
                            
                            matching_in_moves = req.picking_in_id.move_ids.filtered(
                                lambda m: m.product_id == out_move.product_id
                            )
                            for in_move in matching_in_moves:
                                if cost:
                                    in_move.sudo().write({'price_unit': cost})
                                    to_comp = in_move.company_id
                                    if in_move.product_id.with_company(to_comp).standard_price == 0:
                                        in_move.product_id.with_company(to_comp).sudo().standard_price = cost

                    if is_return:
                        msg = _("تم اعتماد صرف مرتجع الفرع (%s). البضاعة الآن في الطريق إلى مخزن المرتجعات عبر المخزن الوسيط.") % picking.name
                    else:
                        msg = _("تم اعتماد صرف الشحنة من المخزن المصروف منه (%s). البضاعة الآن في الطريق إلى مخزن الفرع عبر المخزن الوسيط.") % picking.name
                    req.message_post(body=msg)
                elif picking == req.picking_in_id:
                    req.write({'state': 'done'})
                    if is_return:
                        msg = _("تم استلام المرتجع وتخزينه في مخزن المرتجعات (%s). اكتمل طلب المرتجع بنجاح.") % picking.name
                    else:
                        msg = _("تم استلام البضاعة وتخزينها في مخزن الفرع (%s). اكتمل طلب التحويل بنجاح.") % picking.name
                    req.message_post(body=msg)
        return res


class StockMove(models.Model):
    _inherit = 'stock.move'

    def _get_price_unit(self):
        self.ensure_one()
        # For inbound inter-branch moves received from transit: inherit exact cost from outbound move
        if self.picking_id.inter_branch_request_id and self.location_id.usage == 'transit':
            req = self.picking_id.inter_branch_request_id
            if req.picking_out_id:
                out_move = req.picking_out_id.move_ids.filtered(lambda m: m.product_id == self.product_id)
                if out_move:
                    svls = out_move.sudo().stock_valuation_layer_ids
                    if svls:
                        qty = sum(svls.mapped('quantity'))
                        val = sum(svls.mapped('value'))
                        if qty:
                            cost = abs(val / qty)
                            if self.product_id.lot_valuated:
                                return dict.fromkeys(self.lot_ids, cost)
                            return {self.env['stock.lot']: cost}
                    if out_move[0].price_unit:
                        if self.product_id.lot_valuated:
                            return dict.fromkeys(self.lot_ids, out_move[0].price_unit)
                        return {self.env['stock.lot']: out_move[0].price_unit}
                    src_comp = out_move[0].company_id
                    src_std = self.product_id.with_company(src_comp).standard_price
                    if src_std:
                        if self.product_id.lot_valuated:
                            return dict.fromkeys(self.lot_ids, src_std)
                        return {self.env['stock.lot']: src_std}
        return super()._get_price_unit()

    def _get_dest_account(self, accounts_data):
        self.ensure_one()
        # For outbound inter-branch moves heading into transit: use account 6125 (transit clearing)
        if self.picking_id.inter_branch_request_id and self.location_dest_id.usage == 'transit':
            transit_acc = self.env['account.account'].search([
                ('code', '=', '6125'),
                ('company_ids', 'in', [self.company_id.id])
            ], limit=1)
            if transit_acc:
                return transit_acc.id
        return super()._get_dest_account(accounts_data)

    def _get_src_account(self, accounts_data):
        self.ensure_one()
        # For inbound inter-branch moves received from transit: use account 6125 (transit clearing)
        if self.picking_id.inter_branch_request_id and self.location_id.usage == 'transit':
            transit_acc = self.env['account.account'].search([
                ('code', '=', '6125'),
                ('company_ids', 'in', [self.company_id.id])
            ], limit=1)
            if transit_acc:
                return transit_acc.id
        return super()._get_src_account(accounts_data)

    def _prepare_account_move_line(self, qty, cost, credit_account_id, debit_account_id, svl_id, description):
        self.ensure_one()
        if self.picking_id.inter_branch_request_id:
            transit_acc = self.env['account.account'].search([
                ('code', '=', '6125'),
                ('company_ids', 'in', [self.company_id.id])
            ], limit=1)
            if transit_acc:
                if self.location_dest_id.usage == 'transit':
                    debit_account_id = transit_acc.id
                elif self.location_id.usage == 'transit':
                    credit_account_id = transit_acc.id
        return super()._prepare_account_move_line(qty, cost, credit_account_id, debit_account_id, svl_id, description)
