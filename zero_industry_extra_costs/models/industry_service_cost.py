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
from odoo.exceptions import UserError, ValidationError
from odoo.osv.expression import AND, OR

from operator import itemgetter
from re import findall as regex_findall

from odoo.osv import expression
from collections import defaultdict

from dateutil.relativedelta import relativedelta
import json
import datetime
import math
import re

from ast import literal_eval

from odoo.addons.web.controllers.utils import clean_action
from odoo.tools import float_compare, float_round, float_is_zero, format_datetime
from odoo.tools.misc import OrderedSet, clean_context, format_date, groupby as tools_groupby

ACCOUNT_DOMAIN = "['&', ('deprecated', '=', False), ('account_type', 'not in', ('asset_receivable','liability_payable','asset_cash','liability_credit_card','off_balance'))]"

class MrpBomLine(models.Model):
    _inherit = 'mrp.bom.line'
    
    unit_cost = fields.Float(string='Cost/Unit',related='product_tmpl_id.standard_price', store=True)
    total_cost = fields.Float(string='Total Cost/BOM Unit',compute='_compute_total_cost', store=True)
    sub_total_cost = fields.Float(string='SubTotal',compute='_compute_sub_total_cost', store=True)
    qty_bom_unit = fields.Float(help='Quantity/BOM Unit', compute='_comput_qty',digits='Product Unit of Measure',store=True)
    
    @api.depends('product_qty', 'unit_cost')
    def _compute_sub_total_cost(self):
        for rec in self:
            rec.sub_total_cost = rec.product_qty * rec.unit_cost
            

    @api.depends('product_qty','bom_id.product_qty')
    def _comput_qty(self):
        for bom in self:
            if bom.bom_id.product_qty >0:
                bom.qty_bom_unit = bom.product_qty / bom.bom_id.product_qty


    @api.depends('qty_bom_unit', 'unit_cost')
    def _compute_total_cost(self):
        for rec in self:
            rec.total_cost = rec.qty_bom_unit * rec.unit_cost

class MrpBom(models.Model):
    _inherit = 'mrp.bom'


    total_bom_cost = fields.Float(compute='_compute_total_bom_cost',string='Total BOM Cost',store=True)
    service_cost_ids = fields.One2many('industry.service.cost', 'bom_id', 'Variable OverHead', copy=True)
    total_service_cost = fields.Float(compute='_compute_total_service_cost',string='Total Variable OverHead Costs',store=True)
    total_material_cost = fields.Float(compute='_compute_total_material_cost',string='Total Materials Costs',store=True)

   
    bom_product_uom_qty = fields.Float(
        string="BOM UOM Quantity",
        digits='Product Unit of Measure',compute='compute_bom_product_uom_qty')

    @api.depends('product_tmpl_id','product_uom_id', 'product_qty','product_tmpl_id.uom_id')
    def compute_bom_product_uom_qty(self):
        for bom in self:
            if bom.product_tmpl_id.uom_id != bom.product_uom_id:
                bom.bom_product_uom_qty = bom.product_uom_id._compute_quantity(bom.product_qty, bom.product_tmpl_id.uom_id)
            else:
                bom.bom_product_uom_qty =  bom.product_qty
    
    bom_unit_factor = fields.Float('Unit Factor', compute='_compute_unit_factor',store=True)

    @api.depends('bom_product_uom_qty','product_qty','product_uom_id','product_tmpl_id','product_tmpl_id.uom_id')
    def _compute_unit_factor(self):
        for bom in self:
            if bom.product_tmpl_id.uom_id != bom.product_uom_id:
                bom.bom_unit_factor = (bom.bom_product_uom_qty / bom.product_qty)
            if bom.product_tmpl_id.uom_id == bom.product_uom_id:
                bom.bom_unit_factor = 1.00

    @api.depends('service_cost_ids.total_cost')
    def _compute_total_service_cost(self):
        for result in self:
            result.ensure_one()
            result.total_service_cost = 0.00
            if result.service_cost_ids:
                result.total_service_cost = sum(
                    result.service_cost_ids.mapped('total_cost'))

    @api.depends('bom_line_ids.unit_cost')
    def _compute_total_material_cost(self):
        for result in self:
            result.ensure_one()
            result.total_material_cost = 0.00
            if result.bom_line_ids:
                result.total_material_cost = sum(
                    result.bom_line_ids.mapped('unit_cost'))

    @api.depends('total_material_cost', 'total_service_cost')
    def _compute_total_bom_cost(self):
        for rec in self:
            rec.total_bom_cost = rec.total_material_cost + rec.total_service_cost


    @api.model
    def _bom_service_find_domain(self, products, company_id=False, bom_type=False):
        domain = ['&', '|', ('product_id', 'in', products.ids), '&', ('product_id', '=', False), ('product_tmpl_id', 'in', products.product_tmpl_id.ids), ('active', '=', True)]
        if company_id or self.env.context.get('company_id'):
            domain = AND([domain, ['|', ('company_id', '=', False), ('company_id', '=', company_id or self.env.context.get('company_id'))]])
        if bom_type:
            domain = AND([domain, [('type', '=', bom_type)]])
        return domain

    @api.model
    def _bom_service_find(self, products, company_id=False, bom_type=False):
        bom_by_product = defaultdict(lambda: self.env['mrp.bom'])
        products = products.filtered(lambda p: p.type == 'service')
        if not products:
            return bom_by_product
        domain = self._bom_service_find_domain(products, company_id=company_id, bom_type=bom_type)

        if len(products) == 1:
            bom = self.search(domain, order='sequence, product_id, id', limit=1)
            if bom:
                bom_by_product[products] = bom
            return bom_by_product

        boms = self.search(domain, order='sequence, product_id, id')

        products_ids = set(products.ids)
        for bom in boms:
            products_implies = bom.product_id or bom.product_tmpl_id.product_variant_ids
            for product in products_implies:
                if product.id in products_ids and product not in bom_by_product:
                    bom_by_product[product] = bom

        return bom_by_product

class IndustryBomServiceCost(models.Model):
    _name = 'industry.service.cost'
    _order = 'reference, mrp_overhead_type_id, sequence, id'
    _description = 'Bill of Material Variable OverHead Costs'
    _rec_name ='reference'
    _check_company_auto = True

  
    sequence = fields.Integer('Sequence', default=10)
    reference = fields.Char(string="Reference",compute='_compute_reference', store=True)
    bom_id = fields.Many2one(
        'mrp.bom', 'BOM',
        index=True, ondelete='cascade', required=True)
    bom_type = fields.Selection(
        related='bom_id.type',
        string="BoM Type",
        copy=False, store=True, precompute=True)
    company_currency_id = fields.Many2one(
        string='Company Currency',
        related='company_id.currency_id', readonly=True, store=True,
    )


    product_id = fields.Many2one('product.product', 'Variable OverHead', required=True, check_company=True, domain="[('type', 'in', ['service'])]",)
    product_tmpl_id = fields.Many2one('product.template', 'Variable OverHead Item', related='product_id.product_tmpl_id', store=True, index=True)

    mrp_overhead_type_id = fields.Many2one('mrp.overhead.type' ,related='product_tmpl_id.mrp_overhead_type_id', string='OverHead Type', store=True, index=True)
    company_id = fields.Many2one(
        related='bom_id.company_id', store=True, index=True, readonly=True)
    price_unit = fields.Float('Unit Cost', related='product_tmpl_id.standard_price',store=True)
    total_cost = fields.Float(compute='_compute_total_cost', store=True,string='Total Cost/BOM Unit')
    sub_total_cost = fields.Float(compute='_compute_sub_total_cost', store=True,string='SubTotal')
    product_uom_id = fields.Many2one(
        'uom.uom', 'Product Unit of Measure',
        required=True,related='product_tmpl_id.uom_id')
    user_id = fields.Many2one(
        'res.users', 'BOM Responsible', default=lambda self: self.env.user,
        domain=lambda self: [('groups_id', 'in', self.env.ref('mrp.group_mrp_user').id)])
    product_qty = fields.Float(
        'Quantity', default=1.0,
        digits='Product Unit of Measure', required=True)
    unbiled_product_qty = fields.Float(
        'Unbiled Quantity', related='product_qty',
        digits='Product Unit of Measure', required=False,store=True,readonly=False)
    qty_bom_unit = fields.Float(
        string='Quantity/BOM Unit', compute='_comput_qty',
        digits='Product Unit of Measure',store=True)
    each_unit_product_uom_qty = fields.Float(
        string="Quantity for each one uom_id unit",
        compute='_compute_each_unit_product_uom_qty',
        digits='Product Unit of Measure',store=True)
    child_bom_id = fields.Many2one(
        'mrp.bom', 'Sub BoM', compute='_compute_child_bom_id')
    child_line_ids = fields.One2many(
        'mrp.bom.line', string="BOM lines of the referred bom",
        compute='_compute_child_line_ids')
    parent_product_tmpl_id = fields.Many2one('product.template', 'Parent Product Template', related='bom_id.product_tmpl_id')
    allowed_operation_ids = fields.One2many('mrp.routing.workcenter', related='bom_id.operation_ids')
    operation_id = fields.Many2one(
        'mrp.routing.workcenter', 'Applied in Operation', check_company=True,
        domain="[('id', 'in', allowed_operation_ids)]",
        help="The operation where the Variable OverHeads are Applied, or the finished products created.")

    @api.depends('bom_id', 'bom_id.code','bom_id.product_tmpl_id')
    def _compute_reference(self):
        for move in self:
            if move.bom_id:
                if move.bom_id.code:
                    move.reference = move.bom_id.code
                else:
                    move.reference = move.bom_id.product_tmpl_id.name

    @api.depends('product_qty', 'price_unit')
    def _compute_sub_total_cost(self):
        for rec in self:
            rec.sub_total_cost = rec.product_qty * rec.price_unit

    @api.depends('product_qty','bom_id.product_qty')
    def _comput_qty(self):
        for bom in self:
            if bom.bom_id.product_qty >0:
                bom.qty_bom_unit = bom.product_qty / bom.bom_id.product_qty

    @api.depends('child_bom_id')
    def _compute_child_line_ids(self):
        for line in self:
            line.child_line_ids = line.child_bom_id.service_cost_ids.ids or False

    @api.depends('product_id', 'bom_id')
    def _compute_child_bom_id(self):
        products = self.product_id
        bom_by_product = self.env['mrp.bom']._bom_service_find(products)
        for line in self:
            if not line.product_id:
                line.child_bom_id = False
            else:
                line.child_bom_id = bom_by_product.get(line.product_id, False)
 
    @api.depends('product_qty','bom_id.bom_product_uom_qty','bom_id.product_qty')
    def _compute_each_unit_product_uom_qty(self):
        for bom in self:
            if bom.bom_id.product_qty >0:
                bom.each_unit_product_uom_qty = bom.product_qty / bom.bom_id.bom_product_uom_qty


    _sql_constraints = [
        ('bom_qty_zero', 'CHECK (product_qty>=0)', 'All Variable OverHead quantities must be greater or equal to 0.\n'
            'Lines with 0 quantities can be used as optional lines.!'),
    ]

    @api.depends('qty_bom_unit', 'price_unit')
    def _compute_total_cost(self):
        for rec in self:
            rec.total_cost = rec.qty_bom_unit * rec.price_unit
            
    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            if 'product_id' in values and 'product_uom_id' not in values:
                values['product_uom_id'] = self.env['product.product'].browse(values['product_id']).uom_id.id
        return super(IndustryBomServiceCost, self).create(vals_list)


class IndustryProdServiceCost(models.Model):
    _name = 'industry.production.service.cost'
    _order = 'reference, mrp_overhead_type_id, sequence, id'
    _description = 'Production Order Variable Costs'
    _rec_name ='reference'
    _check_company_auto = True

    sequence = fields.Integer('Sequence', default=10)
    reference = fields.Char(string="Reference",compute='_compute_reference', store=True)

    account_move_ids = fields.One2many('account.move', 'mrp_overhead_cost')
    product_id = fields.Many2one('product.product', 'Variable OverHead', required=True, check_company=True, domain="[('type', 'in', ['service'])]",)
    product_tmpl_id = fields.Many2one('product.template', 'Variable OverHead Item', related='product_id.product_tmpl_id', store=True, index=True)
    mrp_overhead_type_id = fields.Many2one('mrp.overhead.type' ,related='product_tmpl_id.mrp_overhead_type_id', string='OverHead Type', store=True, index=True)
    price_unit = fields.Float('Unit Cost', related='product_tmpl_id.standard_price',store=True)
    total_cost = fields.Float(string='SubTotal',compute='_compute_total_cost',store=True)
    total_planned_cost = fields.Float(string='Standard Costs To Produced Quantity',compute='_compute_total_planned_cost',store=True)
    total_deviation_cost = fields.Float(string='Deviation Cost',compute='_compute_total_deviation_cost',store=True)
    production_id = fields.Many2one(
        'mrp.production', 'Production Order', check_company=True, index='btree_not_null',ondelete='cascade')
    services_unbuild_id = fields.Many2one(
        'mrp.unbuild', 'Unbuild Order', check_company=True, index='btree_not_null',ondelete='cascade')
    kit_production_id = fields.Many2one(
        'bom.products.stock.move', 'KIT Picking Order', check_company=True, index='btree_not_null',ondelete='cascade')
    company_currency_id = fields.Many2one(
        string='Company Currency',
        related='company_id.currency_id', readonly=True, store=True,
    )
    state = fields.Selection(
        related='production_id.state',
        string="MO Order Status",
        copy=False, store=True, precompute=True)
    kit_state = fields.Selection(
        related='kit_production_id.state',
        string="KIT Picking Order Status",
        copy=False, store=True, precompute=True)
    date = fields.Datetime(string="Move Date", compute='compute_date',store=True)
    bom_id = fields.Many2one(
        'mrp.bom', 'Production BOM', compute='compute_bom_id',store=True)

    @api.depends('production_id', 'production_id.name','kit_production_id', 'kit_production_id.reference')
    def _compute_reference(self):
        for move in self:
            if move.production_id and move.production_id.name:
                move.reference = move.production_id.name
            if move.kit_production_id and move.kit_production_id.reference:
                move.reference = move.kit_production_id.reference
            if move.services_unbuild_id and move.services_unbuild_id.name:
                move.reference = move.services_unbuild_id.name

    @api.depends('production_id','kit_production_id')
    def compute_date(self):
        for production in self:
            if production.production_id and production.production_id.date_finished:
                production.date = production.production_id.date_finished
            elif production.kit_production_id and production.kit_production_id.date:
                production.date = production.kit_production_id.date

    @api.depends('production_id','production_id.bom_id','kit_production_id','kit_production_id.bom_id')
    def compute_bom_id(self):
        for production in self:
            if production.production_id and production.production_id.bom_id:
                production.bom_id = production.production_id.bom_id
            elif production.kit_production_id and production.kit_production_id.bom_id:
                production.bom_id = production.kit_production_id.bom_id

    company_id = fields.Many2one('res.company', string='Company',index=True, default=lambda self: self.env.company)
    user_id = fields.Many2one(
        'res.users', 'Responsible', compute='compute_user_id',store=True)

    @api.depends('production_id','production_id.user_id','kit_production_id','kit_production_id.user_id')
    def compute_user_id(self):
        for production in self:
            if production.production_id and production.production_id.user_id:
                production.user_id = production.production_id.user_id
            elif production.kit_production_id and production.kit_production_id.user_id:
                production.user_id = production.kit_production_id.user_id
            else:
                production.user_id = self.env.user.id

    qty_to_complete = fields.Float(
        'Estemated Quantity TO Complete',
        digits='Product Unit of Measure',compute='_compute_qty_to_complete',store=True)
    cost_to_complete = fields.Float('Estemated Cost TO Complete',compute='_compute_cost_to_complete',store=True)
    planned_product_qty = fields.Float(
        'Standard Quantity TO Produce',
        digits='Product Unit of Measure',compute='_compute_planned_product_qty',store=True)
    product_qty = fields.Float(
        'Quantity TO Produce',
        digits='Product Unit of Measure',compute='_compute_product_qty',store=True)
    qty_deviation = fields.Float(
        'Quantity Deviation',
        digits='Product Unit of Measure',compute='_compute_qty_deviation',store=True)
    product_uom_id = fields.Many2one(
        'uom.uom', 'Product Unit of Measure',
        required=True,related='product_tmpl_id.uom_id')
    each_unit_product_uom_qty = fields.Float(
        string="Quantity for each one uom_id unit",
        digits='Product Unit of Measure')
    allowed_operation_ids = fields.One2many(
        'mrp.routing.workcenter', related='production_id.bom_id.operation_ids')
    operation_id = fields.Many2one(
        'mrp.routing.workcenter', 'Operation To Consume', check_company=True,
        domain="[('id', 'in', allowed_operation_ids)]")

    def action_get_account_moves(self):
        self.ensure_one()
        action_data = self.env['ir.actions.act_window']._for_xml_id('account.action_move_journal_line')
        action_data['domain'] = [('id', 'in', self.account_move_ids.ids)]
        return action_data

    @api.depends('qty_to_complete','price_unit')
    def _compute_cost_to_complete(self):
        for production in self:
            production.cost_to_complete = production.price_unit * production.qty_to_complete

    @api.depends('product_qty','production_id.qty_producing','production_id.product_qty')
    def _compute_qty_to_complete(self):
        for production in self:
            if not float_is_zero(production.production_id.qty_producing, precision_rounding=0.0001) and\
            production.production_id.qty_producing >0: 
                production_qty_rate = (production.production_id.product_qty -production.production_id.qty_producing) / production.production_id.qty_producing
                production.qty_to_complete = production_qty_rate * production.product_qty
            else:
                production.qty_to_complete =  production.product_qty

    @api.depends('qty_deviation', 'price_unit')
    def _compute_total_deviation_cost(self):
        for rec in self:
            rec.total_deviation_cost = rec.qty_deviation * rec.price_unit

    @api.depends('product_qty', 'price_unit')
    def _compute_total_cost(self):
        for rec in self:
            if rec.product_qty >0:
                rec.total_cost = rec.product_qty * rec.price_unit
            else:
                rec.total_cost = 0

    @api.depends('planned_product_qty', 'price_unit')
    def _compute_total_planned_cost(self):
        for rec in self:
            rec.total_planned_cost = rec.planned_product_qty * rec.price_unit


    @api.depends('product_qty','planned_product_qty')
    def _compute_qty_deviation(self):
        for bom in self:
            bom.qty_deviation = bom.product_qty - bom.planned_product_qty


    @api.depends('bom_id','each_unit_product_uom_qty','kit_production_id.kit_qty_requested','production_id.product_qty','services_unbuild_id.product_qty', 'production_id.prd_unit_factor','production_id.qty_producing','production_id.show_produce','production_id.show_produce_all')
    def _compute_planned_product_qty(self):
        for bom in self:
            if bom.production_id and bom.bom_id and bom.bom_id.service_cost_ids:
                if bom.production_id.qty_producing >0:
                    bom.planned_product_qty = bom.each_unit_product_uom_qty * (bom.production_id.prd_unit_factor  or 1) * bom.production_id.qty_producing
                if bom.production_id.qty_producing ==0:
                    bom.planned_product_qty = bom.each_unit_product_uom_qty * (bom.production_id.prd_unit_factor  or 1) * bom.production_id.product_qty
            if bom.kit_production_id and bom.bom_id and bom.bom_id.service_cost_ids:
                    bom.planned_product_qty = bom.each_unit_product_uom_qty * bom.kit_production_id.kit_qty_requested

            if bom.services_unbuild_id and bom.bom_id and bom.bom_id.service_cost_ids:
                bom.planned_product_qty = bom.each_unit_product_uom_qty * (bom.services_unbuild_id.prd_unit_factor  or 1) * bom.services_unbuild_id.product_qty


    @api.depends('kit_production_id.kit_qty_delivered','production_id.qty_producing','services_unbuild_id.product_qty')
    def _compute_product_qty(self):
        for bom in self:
            if bom.production_id and bom.bom_id and bom.bom_id.service_cost_ids:
                qty_none_or_all = bom.production_id.qty_producing in (0, bom.production_id.product_qty)
                changed = bom.planned_product_qty - bom.planned_product_qty
                if bom.production_id.qty_producing >0 and bom.state not in('to_close','done') and changed !=0:
                    bom.product_qty = bom.each_unit_product_uom_qty * (bom.production_id.prd_unit_factor  or 1) * bom.production_id.qty_producing
                if bom.production_id.qty_producing ==0:
                    bom.product_qty = bom.each_unit_product_uom_qty * (bom.production_id.prd_unit_factor  or 1) * bom.production_id.product_qty
            elif bom.kit_production_id and bom.bom_id and bom.bom_id.service_cost_ids:
                bom.product_qty = bom.each_unit_product_uom_qty * bom.kit_production_id.kit_qty_delivered
            elif bom.services_unbuild_id and bom.bom_id and bom.bom_id.service_cost_ids:
                bom.product_qty = bom.each_unit_product_uom_qty * (bom.services_unbuild_id.prd_unit_factor  or 1) * bom.services_unbuild_id.product_qty



    _sql_constraints = [
        ('bom_qty_zero', 'CHECK (product_qty>=0)', 'All product quantities must be greater or equal to 0.\n'
            'Lines with 0 quantities can be used as optional lines. \n'
            'You should install the mrp_byproduct module if you want to manage extra products on BoMs!'),
    ]


    @api.model
    def default_get(self, fields_list):
        defaults = super(IndustryProdServiceCost, self).default_get(fields_list)
        if self.env.context.get('default_production_id'):
            production_id = self.env['mrp.production'].browse(self.env.context.get('default_production_id'))
            if production_id.state == 'draft':
                defaults['reference'] = production_id.name
        return defaults
   
    @api.model_create_multi
    def create(self, vals_list):
        mo_id_to_mo = defaultdict(lambda: self.env['mrp.production'])
        product_id_to_product = defaultdict(lambda: self.env['product.product'])
        for values in vals_list:
            mo_id = values.get('production_id', False)
            if mo_id:
                mo = mo_id_to_mo[mo_id]
                if not mo:
                    mo = mo.browse(mo_id)
                    mo_id_to_mo[mo_id] = mo
                if values.get('production_id', False):
                    product = product_id_to_product[values['product_id']]
                    if not product:
                        product = product.browse(values['product_id'])
                    product_id_to_product[values['product_id']] = product
                    values['price_unit'] = product.standard_price
                    continue
        return super().create(vals_list)


        ######################################################### MO Account Move ##############################
    def _prepare_account_move_line(self):
        self = self.with_company(self.company_id)
        for move in self:
            accounts_data = self.product_tmpl_id.get_product_accounts()
            production_accounts_data = move.production_id.product_id.product_tmpl_id.get_product_accounts()
            credit_account_id = accounts_data['indirect_cost'].id
            debit_account_id = production_accounts_data['production'].id
            value = move.total_cost
            reference = move.reference and '%s - %s' % (move.reference, move.product_id.name)
            quantity = move.product_qty
        res = [(0, 0, move_lines) for move_lines in self._generate_valuation_lines_data(debit_account_id,credit_account_id,quantity,reference,value).values()]

        return res


    def _generate_valuation_lines_data(self,debit_account_id,credit_account_id,quantity,reference,value):
        for line in self:
            move_lines ={
                    "product_id": line.product_id.id,
                    "name": line.product_id.name,
                    'product_uom_id': line.product_uom_id.id,
                    "ref": reference,
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

    def create_account_move(self):
        for move in self:
            production_accounts_data = move.production_id.product_id.product_tmpl_id.get_product_accounts()
            journal_id = production_accounts_data['stock_journal'].id
            move_ids = move._prepare_account_move_line()
            AccountMove = self.env["account.move"]
            date = fields.Date.context_today(self)
            if move.total_cost >0:
                account_move = AccountMove.sudo().create(
                        {
                        "journal_id": journal_id,
                        'line_ids': move_ids,
                        "company_id": move.company_id.id,
                        'date': date,
                        "ref": move.reference and '%s - %s' % (move.reference, move.product_id.name),
                        "mrp_overhead_cost": move.id,
                        "move_type": 'entry',
                        }
                    )
                account_move._post()
        ######################################################### KIT Account Move ##############################

    def _prepare_kit_account_move_line(self):
        self = self.with_company(self.company_id)
        for move in self:
            accounts_data = move.product_tmpl_id.get_product_accounts()
            production_accounts_data = move.kit_production_id.product_id.product_tmpl_id.get_product_accounts()
            credit_account_id = accounts_data['indirect_cost'].id
            debit_account_id = accounts_data['stock_output'].id
            quantity = move.product_qty
            valuation_partner_id = move.kit_production_id._get_partner_id_for_valuation_lines()
            value = move.total_cost
            reference = move.reference and '%s - %s' % (move.reference, move.product_id.name)
        res = [(0, 0, move_lines) for move_lines in self._generate_kit_valuation_lines_data(valuation_partner_id,debit_account_id,credit_account_id,quantity,reference,value).values()]

        return res

    def _generate_kit_valuation_lines_data(self,valuation_partner_id,debit_account_id,credit_account_id,quantity,reference,value):
        for line in self:
            move_lines ={
                    "product_id": line.product_id.id,
                    "name": line.product_id.name,
                    'product_uom_id': line.product_uom_id.id,
                    'quantity': quantity,
                    'partner_id': valuation_partner_id,
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

    def create_kit_account_move(self):
        for move in self:
            production_accounts_data = move.kit_production_id.product_id.product_tmpl_id.get_product_accounts()
            journal_id = production_accounts_data['stock_journal'].id
            wip_move_ids = move._prepare_kit_account_move_line()
            AccountMove = self.env["account.move"]
            ref = 'Stock Output Reconciliation of %s' % (move.kit_production_id.picking_id.name)
            date = move.date
            if move.total_cost >0:
                account_move_wip = AccountMove.sudo().create(
                        {
                        "journal_id": journal_id,
                        'line_ids': wip_move_ids,
                        "company_id": move.company_id.id,
                        'date': date,
                        "ref": ref and '%s - %s' % (ref, move.kit_production_id.product_id.name),
                        "mrp_overhead_cost": move.id,
                        "move_type": 'entry',
                        }
                    )
                account_move_wip._post()

        ############################### unbuild order #############################
        #############################Unbuild order ###############################

    def prepare_unbuild_account_move_line(self):
        self = self.with_company(self.company_id)
        for move in self:
            accounts_data = move.product_tmpl_id.get_product_accounts()
            production_accounts_data = move.services_unbuild_id.product_id.product_tmpl_id.get_product_accounts()
            credit_account_id = accounts_data['indirect_cost'].id
            debit_account_id = production_accounts_data['production'].id
            value = move.total_cost
            reference = move.reference and '%s - %s' % (move.reference, move.product_id.name)
            quantity = move.product_qty
        res = [(0, 0, move_lines) for move_lines in self._generate_unbuild_valuation_lines_data(debit_account_id,credit_account_id,quantity,reference,value).values()]

        return res


    def _generate_unbuild_valuation_lines_data(self,debit_account_id,credit_account_id,quantity,reference,value):
        for line in self:
            move_lines ={
                    "product_id": line.product_id.id,
                    "name": line.product_id.name,
                    'product_uom_id': line.product_uom_id.id,
                    "ref": reference,
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

    def create_unbuild_account_move(self):
        for move in self:
            production_accounts_data = move.services_unbuild_id.product_id.product_tmpl_id.get_product_accounts()
            journal_id = production_accounts_data['stock_journal'].id
            move_ids = move.prepare_unbuild_account_move_line()
            AccountMove = self.env["account.move"]
            date = fields.Date.context_today(self)
            if move.total_cost >0:
                account_move = AccountMove.sudo().create(
                        {
                        "journal_id": journal_id,
                        'line_ids': move_ids,
                        "company_id": move.company_id.id,
                        'date': date,
                        "ref": move.reference and '%s - %s' % (move.reference, move.product_id.name),
                        "mrp_overhead_cost": move.id,
                        "move_type": 'entry',
                        }
                    )
                account_move._post()
class BomProductsStockMove(models.Model):
    _inherit = 'bom.products.stock.move'

    services_move_raw_ids = fields.One2many(
        'industry.production.service.cost', 'kit_production_id', 'Variable OverHead',
        compute='_compute_move_raw_ids', store=True,
        copy=False,)

    def _get_partner_id_for_valuation_lines(self):
        return (self.picking_id.partner_id and self.env['res.partner']._find_accounting_partner(self.picking_id.partner_id).id) or False
   

    @api.depends('company_id', 'bom_id', 'product_id', 'kit_qty_delivered','picking_id')
    def _compute_move_raw_ids(self):
        for production in self:
            if production.bom_id and production.product_id and production.bom_id.service_cost_ids and production.kit_qty_delivered > 0:
                production.write({'services_move_raw_ids': [(5, 0)]})
                production.write({
                    'services_move_raw_ids': [
                        (0, 0, {
                            'kit_production_id': production.id,
                            'date': production.date,
                            'bom_id': production.bom_id.id,
                            'product_id': rec.product_id.id,
                            'each_unit_product_uom_qty': rec.each_unit_product_uom_qty,
                        }) for rec in production.bom_id.service_cost_ids.filtered(lambda m: m.product_qty > 0)]
                })
                for order in self:
                    if not self.services_move_raw_ids:
                        continue
                    services_cost = order.services_move_raw_ids
                    for acc in services_cost:
                        if acc.product_id.valuation != 'real_time' and acc.bom_id.total_service_cost >0:
                            acc.create_kit_account_move()


    def overhead_account_entry_count(self):
        return self.env['account.move'].sudo().search_count([('id', 'in', self.services_move_raw_ids.account_move_ids.ids)])

    overhead_entry_count = fields.Integer(compute='_computeoverhead_account_entry_count', string="OverHead Account Entry Count", default=overhead_account_entry_count)

    def _computeoverhead_account_entry_count(self):
        overhead_account_entry_count = self.overhead_account_entry_count()
        for account in self:
            account.overhead_entry_count = overhead_account_entry_count

    def action_get_overhead_account_moves(self):
        self.ensure_one()
        action_data = self.env['ir.actions.act_window']._for_xml_id('account.action_move_journal_line')
        action_data['domain'] = [('id', 'in', self.services_move_raw_ids.account_move_ids.ids)]
        return action_data

class MrpProduction(models.Model):
    _inherit = 'mrp.production'


    def overhead_account_entry_count(self):
        return self.env['account.move'].sudo().search_count([('id', 'in', self.services_move_raw_ids.account_move_ids.ids)])
        
    services_move_raw_ids = fields.One2many('industry.production.service.cost', 'production_id', 'Variable OverHead',copy=True)
    prd_unit_factor = fields.Float(string='Unit Factor', compute='_compute_unit_factor',store=True)
    total_material_cost = fields.Float(string='Demanded Materials Costs',compute='_compute_total_material_cost',store=True)
    product_material_cost = fields.Float(string='Product Unit Share of Materials',compute='_compute_maaterial_cost_product_unit',store=True)
    total_service_cost = fields.Float(string='Demanded Variable OverHead Costs',compute='_compute_total_service_cost',store=True)
    product_service_cost = fields.Float(string='Product Unit Share of OverHead',compute='_compute_service_cost_product_unit',store=True)
    total_prd_cost = fields.Float(string='Manufacturing Order Cost',compute='_compute_total_prd_cost',store=True)
    product_cost = fields.Float(string='Product Unit Cost',compute='_compute_product_cost',store=True)
    total_planned_service_cost = fields.Float(string='Standard Variable OverHead Costs To Produced Quantity',compute='_compute_total_planned_service_cost',store=True)
    total_planned_material_cost = fields.Float(string='Standard Material Costs To Produced Quantity',compute='_compute_total_planned_material_cost',store=True)
    total_material_deviation_cost = fields.Float(compute='_compute_total_material_deviation_cost',string='Materials Deviation Cost')
    total_service_deviation_cost = fields.Float(string='Total Variable OverHead Deviation Costs',compute='_compute_service_total_deviation_cost',store=True)
    total_deviation_cost = fields.Float(compute='_compute_total_deviation_cost',string='Total Deviations Cost')
    qty_to_complete = fields.Float(
        'Remaining Quantity TO Complete',
        digits='Product Unit of Measure', compute='_compute_qty_to_complete',store=True)
    total_service_cost_to_complete = fields.Float(string='Estemated Variable OverHead Cost TO Complete',compute='_compute_service_cost_to_complete',store=True)
    total_material_cost_to_complete = fields.Float(string='Estemated Material Cost TO Complete',compute='_compute_material_cost_to_complete',store=True)
    total_est_prd_cost_to_complete = fields.Float(string='Total Estemated Cost TO Complete Producing',compute='_compute_total_est_prd_cost_to_complete',store=True)
    overhead_entry_count = fields.Integer(compute='_computeoverhead_account_entry_count', string="OverHead Account Entry Count", default=overhead_account_entry_count)


    def _computeoverhead_account_entry_count(self):
        overhead_account_entry_count = self.overhead_account_entry_count()
        for account in self:
            account.overhead_entry_count = overhead_account_entry_count

    def action_get_overhead_account_moves(self):
        self.ensure_one()
        action_data = self.env['ir.actions.act_window']._for_xml_id('account.action_move_journal_line')
        action_data['domain'] = [('id', 'in', self.services_move_raw_ids.account_move_ids.ids)]
        return action_data

    def action_get_material_account_moves(self):
        self.ensure_one()
        action_data = self.env['ir.actions.act_window']._for_xml_id('account.action_move_journal_line')
        action_data['domain'] = [('id', 'in', (self.move_raw_ids + self.move_finished_ids + self.scrap_ids.move_ids).account_move_ids.ids)]
        return dict(action_data)
   

    @api.depends('services_move_raw_ids.total_cost')
    def _compute_total_service_cost(self):
        for result in self:
            result.total_service_cost = sum(
                result.mapped('services_move_raw_ids').mapped('total_cost'))

    @api.depends('total_material_cost', 'qty_producing')
    def _compute_maaterial_cost_product_unit(self):
        for rec in self:
            if rec.qty_producing >0 and rec.total_material_cost >0:
                rec.product_material_cost = rec.total_material_cost  / rec.qty_producing
            else:
                rec.product_material_cost =0

    @api.depends('total_service_cost', 'qty_producing')
    def _compute_service_cost_product_unit(self):
        for rec in self:
            if rec.qty_producing >0 and rec.total_service_cost>0:
                rec.product_service_cost = rec.total_service_cost / rec.qty_producing
            else:
                rec.product_service_cost =0

    @api.depends('services_move_raw_ids.total_planned_cost')
    def _compute_total_planned_service_cost(self):
        for result in self:
            result.total_planned_service_cost = sum(
                result.mapped('services_move_raw_ids').mapped('total_planned_cost'))

    @api.depends('total_material_cost_to_complete', 'total_service_cost_to_complete')
    def _compute_total_est_prd_cost_to_complete(self):
        for rec in self:
            rec.total_est_prd_cost_to_complete = rec.total_material_cost_to_complete + rec.total_service_cost_to_complete

    @api.depends('services_move_raw_ids.cost_to_complete')
    def _compute_service_cost_to_complete(self):
        for result in self:
            result.total_service_cost_to_complete = sum(
                result.mapped('services_move_raw_ids').mapped('cost_to_complete'))

    @api.depends('move_raw_ids.cost_to_complete')
    def _compute_material_cost_to_complete(self):
        for result in self:
            result.total_material_cost_to_complete = sum(
                result.mapped('move_raw_ids').mapped('cost_to_complete'))

    @api.depends('product_qty','qty_producing')
    def _compute_qty_to_complete(self):
        for production in self:
            qty_to_complete = production.product_qty - production.qty_producing

    @api.depends('total_material_deviation_cost','total_service_deviation_cost')
    def _compute_total_deviation_cost(self):
        for bom in self:
            bom.total_deviation_cost = bom.total_material_deviation_cost + bom.total_service_deviation_cost

    @api.depends('move_raw_ids.total_deviation_cost')
    def _compute_total_material_deviation_cost(self):
        for result in self:
            result.total_material_deviation_cost = sum(
                result.mapped('move_raw_ids').mapped('total_deviation_cost'))

    @api.depends('move_raw_ids.total_to_consume_material_cost')
    def _compute_total_planned_material_cost(self):
        for result in self:
            result.total_planned_material_cost = sum(
                result.mapped('move_raw_ids').mapped('total_to_consume_material_cost'))


    @api.depends('services_move_raw_ids.total_deviation_cost')
    def _compute_service_total_deviation_cost(self):
        for result in self:
            result.total_service_deviation_cost = sum(
                result.mapped('services_move_raw_ids').mapped('total_deviation_cost'))


    @api.depends('total_material_cost', 'total_service_cost')
    def _compute_total_prd_cost(self):
        for rec in self:
            rec.total_prd_cost = rec.total_material_cost + rec.total_service_cost

    @api.depends('total_prd_cost', 'qty_producing')
    def _compute_product_cost(self):
        for rec in self:
            if rec.qty_producing >0 and rec.total_prd_cost>0:
                rec.product_cost = rec.total_prd_cost / rec.qty_producing
            else:
                rec.product_cost =0


    @api.depends('move_raw_ids.total_cost')
    def _compute_total_material_cost(self):
        for result in self:
            result.total_material_cost = sum(
                result.mapped('move_raw_ids').mapped('total_cost'))


    def _get_bom_values(self, ratio=1):
        self.ensure_one()

        def get_uom_and_quantity(move):
            # Use the BoM line/by-product's UoM if the move is linked to one of them.
            target_uom = (move.bom_line_id or move.byproduct_id).product_uom_id or move.product_uom
            # In order to be able to multiply the move quantity by the ratio, we
            # have to be sure they both express in the same UoM.
            qty = move.quantity or move.product_uom_qty
            qty = move.product_uom._compute_quantity(qty * ratio, target_uom)
            return (target_uom, qty)

        # BoM lines values.
        bom_lines_values = []
        bom_serves_lines_values = []
        byproduct_values = []
        for move_raw in self.move_raw_ids:
            uom, qty = get_uom_and_quantity(move_raw)
            bom_line_vals = {
                'product_id': move_raw.product_id.id,
                'product_qty': qty,
                'product_uom_id': uom.id,
            }
            bom_lines_values.append(Command.create(bom_line_vals))
        #Variable OverHead lines###
        for move_service_raw in self.services_move_raw_ids:
            bom_service_line_vals = {
                'product_id': move_service_raw.product_id.id,
                'product_qty': move_service_raw.product_qty,
            }
            bom_serves_lines_values.append(Command.create(bom_service_line_vals))
        # By-Product lines values.
        for move_byproduct in self.move_byproduct_ids:
            uom, qty = get_uom_and_quantity(move_byproduct)
            bom_byproduct_vals = {
                'cost_share': move_byproduct.cost_share,
                'product_id': move_byproduct.product_id.id,
                'product_qty': qty,
                'product_uom_id': uom.id,
            }
            byproduct_values.append(Command.create(bom_byproduct_vals))
        # Operations values.
        operations_values = [Command.create(wo._get_operation_values()) for wo in self.workorder_ids]
        return (bom_lines_values, bom_serves_lines_values, byproduct_values, operations_values)

    def action_generate_bom(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('mrp.mrp_bom_form_action')
        action['view_mode'] = 'form'
        action['views'] = [(False, 'form')]
        action['target'] = 'new'

        bom_lines_vals, bom_service_lines_vals, byproduct_vals, operations_vals = self._get_bom_values()
        action['context'] = {
            'default_bom_line_ids': bom_lines_vals,
            'default_service_cost_ids': bom_service_lines_vals,
            'default_byproduct_ids': byproduct_vals,
            'default_code': _("New BoM from %(mo_name)s", mo_name=self.display_name),
            'default_company_id': self.company_id.id,
            'default_operation_ids': operations_vals,
            'default_product_id': self.product_id.id,
            'default_product_qty': self.product_qty,
            'default_product_tmpl_id': self.product_id.product_tmpl_id.id,
            'default_product_uom_id': self.product_uom_id.id,
            'parent_production_id': self.id,  # Used to assign the new BoM to the current MO.
        }
        self._onchange_bom_id()
        return action


    @api.depends('product_uom_qty','product_qty','product_uom_id','product_id','product_id.uom_id')
    def _compute_unit_factor(self):
        for prd in self:
            if prd.product_id:
                if prd.product_id.uom_id != prd.product_uom_id and prd.product_uom_qty >0:
                    prd.prd_unit_factor = (prd.product_uom_qty / prd.product_qty)
                else:
                    prd.prd_unit_factor = 1.00


   
    def copy_data(self, default=None):
        default = dict(default or {})
        if not default or 'services_move_raw_ids' not in default:
            default['services_move_raw_ids'] = [(0, 0, services.copy_data()[0]) for services in self.services_move_raw_ids.filtered(lambda m: m.product_qty != 0.0)]
        return super(MrpProduction, self).copy_data(default=default)

    def action_update_bom(self):
        for production in self:
            if production.bom_id:
                production._link_bom(production.bom_id)
                production._onchange_bom_id()
        self.is_outdated_bom = False


    @api.onchange('bom_id','product_id','product_qty','product_uom_id','product_tmpl_id')
    def _onchange_bom_id(self):
        for production in self:
            if production.bom_id and production.product_id and production.bom_id.service_cost_ids and production.product_qty > 0:
                self.write({'services_move_raw_ids': [(5, 0)]})
                self.write({
                    'services_move_raw_ids': [
                        (0, 0, {
                            'production_id': self.id,
                            'bom_id': self.bom_id.id,
                            'product_id': rec.product_id.id,
                            'each_unit_product_uom_qty': rec.each_unit_product_uom_qty,
                        }) for rec in self.bom_id.service_cost_ids.filtered(lambda m: m.product_qty > 0)]
                })
            if not production.bom_id or not production.bom_id.service_cost_ids:
                production.services_move_raw_ids = False



    def _cal_price(self, consumed_moves):
        finished_move = self.move_finished_ids.filtered(
            lambda x: x.product_id == self.product_id and x.state not in ('done', 'cancel') and x.quantity > 0)
        if finished_move:
            quantity = finished_move.product_uom._compute_quantity(
                finished_move.quantity, finished_move.product_id.uom_id)
            costs = (
                self.total_service_cost
            )
            if costs:
                self.extra_cost = costs / quantity

        return super()._cal_price(consumed_moves)

    def _post_inventory(self, cancel_backorder=False):
        res = super(MrpProduction, self)._post_inventory(cancel_backorder=cancel_backorder)
        for order in self:
            if order.services_move_raw_ids and order.product_id.valuation == 'real_time' or order.bom_id.total_service_cost > 0:
                services_cost = order.services_move_raw_ids
                services_cost.create_account_move()
        return res

class MrpUnbuild(models.Model):
    _inherit = 'mrp.unbuild'

    def overhead_account_entry_count(self):
        return self.env['account.move'].sudo().search_count([('id', 'in', self.services_move_raw_ids.account_move_ids.ids)])
        
    services_move_raw_ids = fields.One2many('industry.production.service.cost', 'services_unbuild_id', readonly=True,string='Variable OverHead')
    product_uom_qty = fields.Float(string='Total Quantity', compute='_compute_product_uom_qty', store=True)
    prd_unit_factor = fields.Float(string='Unit Factor', compute='_compute_unit_factor',store=True)
    total_service_cost = fields.Float(string='Actual Variable OverHead Costs',compute='_compute_total_service_cost',store=True)
    total_planned_service_cost = fields.Float(string='Standard Variable OverHead Costs',compute='_compute_total_planned_service_cost',store=True)
    total_service_deviation_cost = fields.Float(string='Total Variable OverHead Deviation Costs',compute='_compute_service_total_deviation_cost',store=True)
    overhead_entry_count = fields.Integer(compute='_computeoverhead_account_entry_count', string="OverHead Account Entry Count", default=overhead_account_entry_count)


    def _computeoverhead_account_entry_count(self):
        overhead_account_entry_count = self.overhead_account_entry_count()
        for account in self:
            account.overhead_entry_count = overhead_account_entry_count

    def action_get_overhead_account_moves(self):
        self.ensure_one()
        action_data = self.env['ir.actions.act_window']._for_xml_id('account.action_move_journal_line')
        action_data['domain'] = [('id', 'in', self.services_move_raw_ids.account_move_ids.ids)]
        return action_data

    def action_unbuild(self):
        res = super(MrpUnbuild, self).action_unbuild()
        for order in self:
            if order.services_move_raw_ids and order.product_id.valuation == 'real_time' or order.bom_id.total_service_cost > 0:
                services_cost = order.services_move_raw_ids
                services_cost.create_unbuild_account_move()
        return res

    def action_get_material_account_moves(self):
        self.ensure_one()
        action_data = self.env['ir.actions.act_window']._for_xml_id('account.action_move_journal_line')
        action_data['domain'] = [('id', 'in', (self.consume_line_ids + self.produce_line_ids).account_move_ids.ids)]
        return dict(action_data)
   

    @api.depends('services_move_raw_ids.total_deviation_cost')
    def _compute_service_total_deviation_cost(self):
        for result in self:
            result.total_service_deviation_cost = sum(
                result.mapped('services_move_raw_ids').mapped('total_deviation_cost'))

    @api.depends('services_move_raw_ids.total_planned_cost')
    def _compute_total_planned_service_cost(self):
        for result in self:
            result.total_planned_service_cost = sum(
                result.mapped('services_move_raw_ids').mapped('total_planned_cost'))


    @api.depends('services_move_raw_ids.total_cost')
    def _compute_total_service_cost(self):
        for result in self:
            result.total_service_cost = sum(
                result.mapped('services_move_raw_ids').mapped('total_cost'))

    @api.depends('product_uom_id', 'product_qty', 'product_id.uom_id')
    def _compute_product_uom_qty(self):
        for production in self:
            if production.product_id.uom_id != production.product_uom_id:
                production.product_uom_qty = production.product_uom_id._compute_quantity(production.product_qty, production.product_id.uom_id)
            else:
                production.product_uom_qty = production.product_qty

    @api.depends('product_uom_qty','product_qty','product_uom_id','product_id','product_id.uom_id')
    def _compute_unit_factor(self):
        for prd in self:
            if prd.product_id:
                if prd.product_id.uom_id != prd.product_uom_id and prd.product_uom_qty >0:
                    prd.prd_unit_factor = (prd.product_uom_qty / prd.product_qty)
                else:
                    prd.prd_unit_factor = 1.00

    @api.onchange('bom_id','product_id','product_qty','product_uom_id','product_tmpl_id')
    def _onchange_bom_id(self):
        for production in self:
            if production.bom_id and production.product_id and production.bom_id.service_cost_ids and production.product_qty > 0:
                self.write({'services_move_raw_ids': [(5, 0)]})
                self.write({
                    'services_move_raw_ids': [
                        (0, 0, {
                            'services_unbuild_id': self.id,
                            'bom_id': self.bom_id.id,
                            'product_id': rec.product_id.id,
                            'each_unit_product_uom_qty': rec.each_unit_product_uom_qty,
                        }) for rec in self.bom_id.service_cost_ids.filtered(lambda m: m.product_qty > 0)]
                })
            if not production.bom_id or not production.bom_id.service_cost_ids:
                production.services_move_raw_ids = False

class StockMove(models.Model):
    _inherit = 'stock.move'

    
    standard_price = fields.Float(string='Cost/Unit',related='product_tmpl_id.standard_price', store=True)
    total_cost = fields.Float(compute='_compute_total_cost', store=True,string='SubTotal')
    qty_deviation = fields.Float(
        'Quantity Deviation',
        digits='Product Unit of Measure',compute='_compute_qty_deviation',store=True)
    total_deviation_cost = fields.Float(compute='_compute_total_deviation_cost',string='Deviation Cost')
    total_to_consume_material_cost = fields.Float(compute='_compute_total_planned_material_cost',string='Material Costs To Produced Quantity')
    qty_to_complete = fields.Float(
        'Estemated Quantity TO Complete',
        digits='Product Unit of Measure', compute='_compute_qty_to_complete',store=True)
    cost_to_complete = fields.Float('Estemated Cost TO Complete',compute='_compute_cost_to_complete',store=True)

    @api.depends('qty_to_complete','standard_price')
    def _compute_cost_to_complete(self):
        for production in self:
            production.cost_to_complete = production.standard_price * production.qty_to_complete
  

    @api.depends('quantity','production_id.qty_producing','production_id.product_qty')
    def _compute_qty_to_complete(self):
        for production in self:
            production.qty_to_complete =  production.product_uom_qty  - production.quantity

    
    @api.depends('quantity', 'standard_price')
    def _compute_total_planned_material_cost(self):
        for rec in self:
            rec.total_to_consume_material_cost = rec.quantity * rec.standard_price

    @api.depends('qty_deviation', 'standard_price')
    def _compute_total_deviation_cost(self):
        for rec in self:
            rec.total_deviation_cost = rec.qty_deviation * rec.standard_price


    @api.depends('should_consume_qty','quantity')
    def _compute_qty_deviation(self):
        for bom in self:
            bom.qty_deviation = bom.quantity - bom.should_consume_qty

    @api.depends('quantity', 'standard_price')
    def _compute_total_cost(self):
        for rec in self:
            rec.total_cost = rec.quantity * rec.standard_price

    def _action_done(self, cancel_backorder=False):
        res = super(StockMove, self)._action_done(cancel_backorder=cancel_backorder)
        for bom in self.bom_line_id.bom_id:
            if (bom.type != 'phantom' and not self.env.context.get('is_scrap')):
                continue
            bom.mapped('product_tmpl_id').action_bom_cost()
        return res

class ProductCategory(models.Model):
    _inherit = 'product.category'

    property_stock_account_indirect_cost_id = fields.Many2one(
        'account.account', 'Production Indirect Cost Account', company_dependent=True,
        domain=ACCOUNT_DOMAIN, 
        help="""This account will be used as a valuation counterpart for both OverHead and final products for manufacturing orders or Kit Products Deliveries.
                If there are any workcenter/employee costs, this value will remain on the account once the production is completed or Kit Products Delivered.""")

class ProductTemplate(models.Model):
    _inherit = 'product.template'


    property_stock_account_indirect_cost_id = fields.Many2one('account.account', company_dependent=True,
        string="Production Indirect Cost Account",
        domain=ACCOUNT_DOMAIN,
        help="""This account will be used as a valuation counterpart for both OverHead and final products for manufacturing orders or Kit Products Deliveries.
                If there are any workcenter/employee costs, this value will remain on the account once the production is completed or Kit Products Delivered.""")

    def _get_product_accounts(self):
        accounts = super()._get_product_accounts()
        accounts.update({
            'indirect_cost': self.property_stock_account_indirect_cost_id or  self.categ_id.property_stock_account_indirect_cost_id,
        })
        return accounts

class ProductProduct(models.Model):
    _inherit = 'product.product'



    def _compute_bom_price(self, bom, boms_to_recompute=False, byproduct_bom=False):
        self.ensure_one()
        if not bom:
            return 0
        if not boms_to_recompute:
            boms_to_recompute = []
        total = 0
        for opt in bom.operation_ids:
            if opt._skip_operation_line(self):
                continue

            duration_expected = (
                opt.workcenter_id._get_expected_duration(self) +
                opt.time_cycle * 100 / opt.workcenter_id.time_efficiency)
            total += (duration_expected / 60) * opt._total_cost_per_hour()

        for line in bom.bom_line_ids:
            if line._skip_bom_line(self):
                continue

            # Compute recursive if line has `child_line_ids`
            if line.child_bom_id and line.child_bom_id in boms_to_recompute:
                child_total = line.product_id._compute_bom_price(line.child_bom_id, boms_to_recompute=boms_to_recompute)
                total += line.product_id.uom_id._compute_price(child_total, line.product_uom_id) * line.product_qty
            else:
                total += line.product_id.uom_id._compute_price(line.product_id.standard_price, line.product_uom_id) * line.product_qty

            #Variable OverHead cost###
        for serv in bom.service_cost_ids:
            if serv.child_bom_id and serv.child_bom_id in boms_to_recompute:
                services_child_total = serv.product_id._compute_bom_price(serv.child_bom_id, boms_to_recompute=boms_to_recompute)
                total += serv.product_id.uom_id._compute_price(services_child_total, serv.product_uom_id) * serv.product_qty
            else:
                total += serv.product_id.uom_id._compute_price(serv.product_id.standard_price, serv.product_uom_id) * serv.product_qty
        if byproduct_bom:
            byproduct_lines = bom.byproduct_ids.filtered(lambda b: b.product_id == self and b.cost_share != 0)
            product_uom_qty = 0
            for line in byproduct_lines:
                product_uom_qty += line.product_uom_id._compute_quantity(line.product_qty, self.uom_id, round=False)
            byproduct_cost_share = sum(byproduct_lines.mapped('cost_share'))
            if byproduct_cost_share and product_uom_qty:
                return total * byproduct_cost_share / 100 / product_uom_qty
        else:
            byproduct_cost_share = sum(bom.byproduct_ids.mapped('cost_share'))
            if byproduct_cost_share:
                total *= float_round(1 - byproduct_cost_share / 100, precision_rounding=0.0001)
            return bom.product_uom_id._compute_price(total / bom.product_qty, self.uom_id)



class AccountMove(models.Model):
    _inherit = 'account.move'

    mrp_overhead_cost = fields.Many2one('industry.production.service.cost', string='MRP OverHead Move', index='btree_not_null',ondelete='cascade')
