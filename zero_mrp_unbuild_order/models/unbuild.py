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


from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare, float_round, float_is_zero, OrderedSet
from odoo.tools.misc import clean_context


ACCOUNT_DOMAIN = "['&', ('deprecated', '=', False), ('account_type', 'not in', ('asset_receivable','liability_payable','asset_cash','liability_credit_card','off_balance'))]"

class MrpUnbuild(models.Model):
    _inherit = 'mrp.unbuild'


    move_raw_ids = fields.Many2many(
        'stock.move', readonly=True,
        string='Components',copy=False)

    diff_amount = fields.Float(
        string='Profit/loss value',
        readonly=True,copy=False)
    raw_total_cost = fields.Float(
        string='raw material value',
        readonly=True,copy=False)
    pro_total_cost = fields.Float(
        string='product value',
        readonly=True,copy=False)

    @api.depends('company_id','mo_id')
    def _compute_location_id(self):
        for order in self:
            if order.mo_id:
                order.location_id = order.mo_id.location_src_id.id
                order.location_dest_id = order.mo_id.location_dest_id.id
            if order.company_id and not order.mo_id:
                warehouse = self.env['stock.warehouse'].search([('company_id', '=', order.company_id.id)], limit=1)
                if order.location_id.company_id != order.company_id:
                    order.location_id = warehouse.lot_stock_id
                if order.location_dest_id.company_id != order.company_id:
                    order.location_dest_id = warehouse.lot_stock_id
                    
    @api.onchange('product_id','location_id')
    def _onchange_product_id_location(self):
        if self.product_id and self.location_id:
            error = []
            precision = self.env['decimal.precision'].precision_get('Product Unit of Measure')
            available_qty = self.env['stock.quant']._get_available_quantity(self.product_id, self.location_id, self.lot_id, strict=True)
            unbuild_qty = self.product_uom_id._compute_quantity(self.product_qty, self.product_id.uom_id)
            if not float_compare(available_qty, unbuild_qty, precision_digits=precision) > 0:
                error.append(_("The product balance in the storage location from does not allow for a unbuild order!"))
            if error:
                raise UserError('\n'.join(error))



    def action_get_profit_loss_account_moves(self):
        self.ensure_one()
        action_data = self.env['ir.actions.act_window']._for_xml_id('account.action_move_journal_line')
        action_data['domain'] = [('mrp_unbuild_cost', '=', self.id)]
        return action_data

    def action_unbuild(self):
        result=super(MrpUnbuild, self).action_unbuild()
        for move in self:
            if move.produce_line_ids:
                raw_total_cost = 0.00
                pro_total_cost = 0.00
                product_stock_move = self.env['stock.move'].search([('unbuild_id', '=', move.id),('company_id', '=', move.company_id.id),('product_id', '=', move.product_id.id)])
                move_raw_ids = self.env['stock.move'].search([('unbuild_id', '=', move.id),('product_id', '!=', move.product_id.id),('company_id', '=', move.company_id.id)])
                move.move_raw_ids = move_raw_ids
                for acc in move_raw_ids:
                    for line in acc.account_move_ids:
                        raw_total_cost += line.amount_total_signed
                move.raw_total_cost = raw_total_cost
                for pro in product_stock_move:
                    for lin in pro.account_move_ids:
                        pro_total_cost += lin.amount_total_signed
                move.pro_total_cost = pro_total_cost
                for record in self:
                    record.diff_amount = record.pro_total_cost - record.raw_total_cost
                    if record.diff_amount !=0:
                        if (record.product_id.product_tmpl_id.property_stock_account_unbuild_profit_loss_id or  record.product_id.product_tmpl_id.categ_id.property_stock_account_unbuild_profit_loss_id):
                            record.create_account_move()
                        else:
                            raise UserError(_("you must link product with MRP Unbuild Profit/Loss Account"))

        return result

    def create_account_move(self):
        self = self.with_company(self.company_id)
        for move in self:
            production_accounts_data = move.product_id.product_tmpl_id.get_product_accounts()
            journal_id = production_accounts_data['stock_journal'].id
            wip_move_ids = move._prepare_account_move_line()
            AccountMove = self.env["account.move"]
            ref = 'Profit/Loss of %s' % (move.name)
            date = move.create_date
            if move.diff_amount !=0:
                account_move_wip = AccountMove.sudo().create(
                        {
                        "journal_id": journal_id,
                        'line_ids': wip_move_ids,
                        "company_id": move.company_id.id,
                        'date': date,
                        "ref": ref and '%s - %s' % (ref, move.product_id.name),
                        "mrp_unbuild_cost": move.id,
                        "move_type": 'entry',
                        }
                    )
                account_move_wip._post()


    def _prepare_account_move_line(self):
        self = self.with_company(self.company_id)
        for move in self:
            accounts_data = move.product_id.product_tmpl_id.get_product_accounts()
            production_accounts_data = move.product_id.product_tmpl_id.get_product_accounts()
            credit_account_id = accounts_data['production'].id
            debit_account_id = accounts_data['unbuild_profit_loss'].id
            value = move.diff_amount
            reference = move.name and '%s - %s' % (move.name, move.product_id.name)
            quantity = move.product_qty
            if value < 0:
                credit_account_id = accounts_data['unbuild_profit_loss'].id
                debit_account_id = accounts_data['production'].id
        res = [(0, 0, move_lines) for move_lines in self._generate_valuation_lines_data(debit_account_id,credit_account_id,quantity,reference,value).values()]

        return res

    def _generate_valuation_lines_data(self,debit_account_id,credit_account_id,quantity,reference,value):
        for line in self:
            move_lines ={
                    "product_id": line.product_id.id,
                    "name": line.product_id.name,
                    'product_uom_id': line.product_uom_id.id,
                    'quantity': quantity,
                    }
            result = {
                'credit_line_vals': {
                    **move_lines,
                    'balance': -value,
                    'account_id': credit_account_id,
                },
                'debit_line_vals': {
                    **move_lines,
                    'balance': value,
                    'account_id': debit_account_id,
                },
            }
        return result

  
class AccountMove(models.Model):
    _inherit = 'account.move'

    mrp_unbuild_cost = fields.Many2one('mrp.unbuild', string='MRP Unbuild Order', index='btree_not_null')


class ProductCategory(models.Model):
    _inherit = 'product.category'

    property_stock_account_unbuild_profit_loss_id = fields.Many2one(
        'account.account', 'MRP Unbuild Profit/Loss Account', company_dependent=True,
        domain=ACCOUNT_DOMAIN, 
        help="""This Account will be used if the product value in the MRP Unbuild order is different from the total value of the raw materials in its bill of materials.""")

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    property_stock_account_unbuild_profit_loss_id = fields.Many2one('account.account', company_dependent=True,
        string="MRP Unbuild Profit/Loss Account",
        domain=ACCOUNT_DOMAIN,
        help="""This Account will be used if the product value in the MRP Unbuild order is different from the total value of the raw materials in its bill of materials.""")

    def _get_product_accounts(self):
        accounts = super()._get_product_accounts()
        accounts.update({
            'unbuild_profit_loss': self.property_stock_account_unbuild_profit_loss_id or  self.categ_id.property_stock_account_unbuild_profit_loss_id,
        })
        return accounts
