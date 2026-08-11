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
        
class OverHeadType(models.Model):
    _name = 'mrp.overhead.type'
    _description = 'MRP OverHead Type'
    _inherit = ['image.mixin','portal.mixin', 'mail.thread', 'mail.activity.mixin']
    _rec_name = 'name'
    _check_company_auto = True

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    description = fields.Text(string='Description', translate=True)
    more_details = fields.Html(string='More Details', translate=True,store=True)
    company_id = fields.Many2one('res.company', string='Company',index=True, default=lambda self: self.env.company)
    product_ids = fields.One2many('product.product','mrp_overhead_type_id', string='OverHead Items')
    color = fields.Integer(string='Color Index', default=0)

    services_count = fields.Integer(
        '# OverHead Item', compute='_compute_services_count',
        help="The number of Variable OverHead under this Type")

    @api.depends('product_ids')
    def _compute_services_count(self):
        for rec in self:
            rec.services_count = len(rec.product_ids)

    def redirect_Services(self,context=None):
        return {
            'type': 'ir.actions.act_window',
            'name': 'OverHead Items',
            'view_mode': 'tree,form',
            'res_model': 'product.product',
            'domain': [('mrp_overhead_type_id','=',self.id)],
            'target': 'current',
            'context': dict(self._context, default_mrp_overhead_type_id=self.id),
        }
    def redirect_mo(self,context=None):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Manufacturing Order',
            'view_mode': 'tree,pivot,graph',
            'res_model': 'industry.production.service.cost',
            'domain': [('mrp_overhead_type_id','=',self.id),('state','!=','cancel')],
            'target': 'current',
            'context': dict(self._context, default_mrp_overhead_type_id=self.id, default_group_by="state"),
        }
    def redirect_bom(self,context=None):
        return {
            'type': 'ir.actions.act_window',
            'name': 'BOM',
            'view_mode': 'tree',
            'res_model': 'industry.service.cost',
            'domain': [('mrp_overhead_type_id','=',self.id)],
            'target': 'current',
            'context': dict(self._context, default_mrp_overhead_type_id=self.id),
        }

class ProductTemplate(models.Model):
    _inherit = 'product.template'


    mrp_overhead_type_id = fields.Many2one('mrp.overhead.type' , compute='_compute_mrp_overhead_type_id',inverse='_set_mrp_overhead_type_id', string='OverHead Type')

    @api.depends('product_variant_ids.mrp_overhead_type_id')
    def _compute_mrp_overhead_type_id(self):
        self.mrp_overhead_type_id = False
        for template in self:
            variant_count = len(template.product_variant_ids)
            if variant_count == 1:
                template.mrp_overhead_type_id = template.product_variant_ids.mrp_overhead_type_id
            elif variant_count == 0:
                archived_variants = template.with_context(active_test=False).product_variant_ids
                if len(archived_variants) == 1:
                    template.mrp_overhead_type_id = archived_variants.mrp_overhead_type_id

    def _set_mrp_overhead_type_id(self):
        variant_count = len(self.product_variant_ids)
        if variant_count == 1:
            self.product_variant_ids.mrp_overhead_type_id = self.mrp_overhead_type_id
        elif variant_count == 0:
            archived_variants = self.with_context(active_test=False).product_variant_ids
            if len(archived_variants) == 1:
                archived_variants.mrp_overhead_type_id = self.mrp_overhead_type_id

    def _get_related_fields_variant_template(self):
        return ['mrp_overhead_type_id','mrp_overhead_type_id', 'default_code', 'standard_price', 'volume', 'weight', 'packaging_ids']
        


class ProductProduct(models.Model):
    _inherit = 'product.product'

    mrp_overhead_type_id = fields.Many2one('mrp.overhead.type' , string='OverHead Type')
    