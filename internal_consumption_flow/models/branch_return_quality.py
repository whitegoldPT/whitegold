# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
import logging

_logger = logging.getLogger(__name__)

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    is_retwh_receipt = fields.Boolean(
        string='مرتجع إلى مخزن المرتجعات',
        compute='_compute_is_retwh_receipt',
        store=True,
        help='تحدد ما إذا كانت الشحنة واردة أو متجهة إلى مخزن المرتجعات (RETWH)'
    )

    @api.depends('location_dest_id', 'picking_type_id')
    def _compute_is_retwh_receipt(self):
        for picking in self:
            dest = picking.location_dest_id
            pt = picking.picking_type_id
            is_ret = False
            if dest:
                wh_code = dest.warehouse_id.code if dest.warehouse_id else ''
                loc_name = dest.complete_name or dest.name or ''
                # BUG-3 FIX: Only rely on RETWH warehouse code, not Arabic name substring
                # (Arabic name match causes false positives for any location named 'مرتجع')
                if wh_code == 'RETWH' or 'RETWH' in loc_name:
                    is_ret = True
            if pt and pt.warehouse_id and pt.warehouse_id.code == 'RETWH':
                is_ret = True
            picking.is_retwh_receipt = is_ret

    def action_view_quality_checks(self):
        # BUG-4 FIX: Handle all combinations of checks and returns correctly
        self.ensure_one()
        checks = self.quality_product_check_ids
        returns = self.quality_return_ids
        if len(checks) == 1 and not returns:
            return {
                'name': 'فحص الجودة',
                'type': 'ir.actions.act_window',
                'res_model': 'quality.product.check',
                'res_id': checks[0].id,
                'view_mode': 'form',
            }
        elif len(returns) == 1 and not checks:
            return {
                'name': 'مرتجع الجودة',
                'type': 'ir.actions.act_window',
                'res_model': 'mrp.production.return',
                'res_id': returns[0].id,
                'view_mode': 'form',
            }
        elif returns and not checks:
            return {
                'name': 'مرتجعات الجودة للشحنة',
                'type': 'ir.actions.act_window',
                'res_model': 'mrp.production.return',
                'domain': [('picking_id', '=', self.id)],
                'view_mode': 'list,form',
            }
        elif checks and not returns:
            return {
                'name': 'فحوصات الجودة للشحنة',
                'type': 'ir.actions.act_window',
                'res_model': 'quality.product.check',
                'domain': [('picking_id', '=', self.id)],
                'view_mode': 'list,form',
            }
        else:
            # BUG-4 FIX: Mixed case — both returns and QPC exist. Show returns (main model)
            return {
                'name': 'فحوصات وطلبات الجودة للشحنة',
                'type': 'ir.actions.act_window',
                'res_model': 'mrp.production.return',
                'domain': [('picking_id', '=', self.id)],
                'view_mode': 'list,form',
            }

    def action_create_quality_check(self):
        """Create quality return records for all move products in the picking that don't have one yet."""
        self.ensure_one()
        if not self.move_ids:
            raise ValidationError("لا يمكن إنشاء طلب جودة لحركة فارغة.")

        created_returns = self.env['mrp.production.return']
        existing_product_ids = self.quality_return_ids.mapped('product_id.id')

        for product in self.move_ids.mapped('product_id'):
            if product.id in existing_product_ids:
                continue

            matching_moves = self.move_ids.filtered(lambda m: m.product_id == product)
            qty = sum(matching_moves.mapped('product_uom_qty')) or sum(matching_moves.mapped('quantity'))
            lot = False
            for m in matching_moves:
                for ml in m.move_line_ids:
                    if ml.lot_id:
                        lot = ml.lot_id
                        break
                if lot:
                    break

            partner = self.partner_id or self.company_id.partner_id or self.env.user.partner_id

            q_return = self.env['mrp.production.return'].sudo().create({
                'partner_id': partner.id,
                'product_id': product.id,
                'qty': qty if qty > 0 else 1.0,
                'lot_id': lot.id if lot else False,
                'uom_id': product.uom_id.id,
                'picking_id': self.id,
                'company_id': self.company_id.id,
                'status': 'draft',
            })
            created_returns |= q_return

        if created_returns and not self.quality_return_id:
            self.write({'quality_return_id': created_returns[0].id})

        if len(self.quality_return_ids) == 1:
            return {
                'name': 'طلب فحص الجودة',
                'type': 'ir.actions.act_window',
                'res_model': 'mrp.production.return',
                'res_id': self.quality_return_ids[0].id,
                'view_mode': 'form',
                'target': 'current',
            }
        else:
            return self.action_view_quality_checks()

    def button_validate(self):
        for picking in self:
            # 1. Check if entering RETWH: Must have approved quality check
            if picking.is_retwh_receipt:
                # If quality checks not yet generated, auto-generate them
                if not picking.quality_return_ids:
                    picking.action_create_quality_check()

                unapproved_returns = picking.quality_return_ids.filtered(lambda r: r.status != 'approved')
                if unapproved_returns:
                    names = ", ".join(unapproved_returns.mapped('name'))
                    raise ValidationError(
                        f"لا يمكن اعتماد استلام المرتجع مخزنياً ({picking.name}) لأن طلبات فحص الجودة المرتبطة به "
                        f"({names}) لم يتم الموافقة عليها واعتمادها من قبل إدارة الجودة بعد."
                    )

        res = super(StockPicking, self).button_validate()

        # Post-validation execution for all attached quality returns:
        for picking in self:
            for q_ret in picking.quality_return_ids.filtered(lambda r: r.status == 'approved'):
                # 1. Handle scrap: execute deferred scrap from picking's destination location
                if q_ret.disposition == 'scrap' and not q_ret.scrap_id:
                    comp_id = q_ret.company_id.id or self.env.company.id
                    scrap_loc = self.env['stock.location'].search([
                        ('scrap_location', '=', True),
                        ('company_id', '=', comp_id)
                    ], limit=1) or self.env['stock.location'].search([
                        ('scrap_location', '=', True)
                    ], limit=1)
                    
                    scrap = self.env['stock.scrap'].sudo().create({
                        'product_id': q_ret.product_id.id,
                        'product_uom_id': (q_ret.uom_id or q_ret.product_id.uom_id).id,
                        'scrap_qty': q_ret.qty,
                        'lot_id': q_ret.lot_id.id if q_ret.lot_id else False,
                        'location_id': picking.location_dest_id.id,
                        'scrap_location_id': scrap_loc.id if scrap_loc else False,
                        'origin': q_ret.name,
                        'company_id': comp_id,
                        'picking_id': picking.id,
                    })
                    scrap.sudo().action_validate()
                    q_ret.scrap_id = scrap.id

                # 2. Handle reprocess: ensure consumed in target MO
                elif q_ret.disposition == 'reprocess' and q_ret.production_id:
                    mo = q_ret.production_id
                    uom = q_ret.uom_id or q_ret.product_id.uom_id
                    existing_move = self.env['stock.move'].search([
                        ('raw_material_production_id', '=', mo.id),
                        ('origin', '=', q_ret.name),
                        ('product_id', '=', q_ret.product_id.id)
                    ], limit=1)
                    if not existing_move:
                        move_vals = {
                            'name': f'مرتجع: {q_ret.name} - {q_ret.product_id.display_name}',
                            'product_id': q_ret.product_id.id,
                            'product_uom_qty': q_ret.qty,
                            'product_uom': uom.id,
                            'location_id': mo.location_src_id.id,
                            'location_dest_id': mo.production_location_id.id,
                            'raw_material_production_id': mo.id,
                            'origin': q_ret.name,
                            'state': 'done',
                            'company_id': mo.company_id.id,
                            'picking_type_id': mo.picking_type_id.id,
                            'is_customer_return': True,
                            'quantity': q_ret.qty,
                        }
                        if q_ret.lot_id:
                            move_vals['lot_id'] = q_ret.lot_id.id
                            move_vals['move_line_ids'] = [(0, 0, {
                                'product_id': q_ret.product_id.id,
                                'lot_id': q_ret.lot_id.id,
                                'quantity': q_ret.qty,
                                'product_uom_id': uom.id,
                                'location_id': mo.location_src_id.id,
                                'location_dest_id': mo.production_location_id.id,
                                'company_id': mo.company_id.id,
                                'state': 'done',
                            })]
                        self.env['stock.move'].sudo().create(move_vals)

                # 3. Handle resale/intermediate transfer if destination differs from receipt location
                elif q_ret.disposition in ('resale', 'intermediate') and q_ret.dest_location_id:
                    if picking.location_dest_id != q_ret.dest_location_id:
                        existing_tr = self.env['stock.move'].search([
                            ('origin', '=', f"توجيه الجودة: {q_ret.name}"),
                            ('product_id', '=', q_ret.product_id.id)
                        ], limit=1)
                        if not existing_tr:
                            warehouse = self.env['stock.warehouse'].search(
                                [('company_id', '=', q_ret.company_id.id or self.env.company.id)], limit=1
                            )
                            uom = q_ret.uom_id or q_ret.product_id.uom_id
                            int_picking = self.env['stock.picking'].sudo().create({
                                'partner_id': q_ret.partner_id.id,
                                'picking_type_id': warehouse.int_type_id.id,
                                'location_id': picking.location_dest_id.id,
                                'location_dest_id': q_ret.dest_location_id.id,
                                'origin': f"توجيه الجودة: {q_ret.name}",
                                'move_ids': [(0, 0, {
                                    'name': q_ret.product_id.display_name,
                                    'product_id': q_ret.product_id.id,
                                    'product_uom_qty': q_ret.qty,
                                    'product_uom': uom.id,
                                    'location_id': picking.location_dest_id.id,
                                    'location_dest_id': q_ret.dest_location_id.id,
                                    'move_line_ids': [(0, 0, {
                                        'product_id': q_ret.product_id.id,
                                        'lot_id': q_ret.lot_id.id if q_ret.lot_id else False,
                                        'quantity': q_ret.qty,
                                        'product_uom_id': uom.id,
                                        'location_id': picking.location_dest_id.id,
                                        'location_dest_id': q_ret.dest_location_id.id,
                                    })] if q_ret.lot_id else [],
                                })],
                            })
                            if not q_ret.lot_id:
                                int_picking.move_ids.quantity = q_ret.qty
                            int_picking.sudo().with_context(skip_quality_check_validation=True).button_validate()

        return res

    def action_return_to_retwh(self):
        """Action button to return goods directly to Returns Warehouse (RETWH)."""
        self.ensure_one()
        ret_wh = self.env['stock.warehouse'].sudo().search([('code', '=', 'RETWH')], limit=1)
        ret_loc = ret_wh.lot_stock_id if ret_wh else self.env['stock.location'].sudo().search([('complete_name', 'ilike', 'RETWH/Stock')], limit=1)
        
        ctx = dict(self.env.context)
        ctx.update({
            'active_id': self.id,
            'active_ids': self.ids,
            'active_model': 'stock.picking',
            'default_location_id': ret_loc.id if ret_loc else False,
        })
        return {
            'name': 'إرجاع إلى مخزن المرتجعات (RETWH)',
            'view_mode': 'form',
            'res_model': 'stock.return.picking',
            'type': 'ir.actions.act_window',
            'target': 'new',
            'context': ctx,
        }


class MrpProductionReturnInherit(models.Model):
    _inherit = 'mrp.production.return'

    def _action_scrap(self):
        """Override scrap: defer scrap execution if incoming receipt picking is not done yet."""
        self.ensure_one()
        if self.picking_id and self.picking_id.state != 'done':
            # Do NOT validate scrap now because goods are not physically in warehouse yet!
            # Execution is deferred cleanly until the receiving picking is validated.
            _logger.info("Quality return %s scrap deferred until picking %s is validated.", self.name, self.picking_id.name)
            return
        return super(MrpProductionReturnInherit, self)._action_scrap()

    def _action_move_to_location(self):
        """Override to ensure resale moves goods to FGWH if no custom destination specified."""
        for rec in self:
            if rec.disposition == 'resale' and not rec.dest_location_id:
                fgwh = self.env['stock.warehouse'].sudo().search([
                    ('code', '=', 'FGWH'),
                    ('company_id', '=', rec.company_id.id or self.env.company.id)
                ], limit=1)
                if fgwh:
                    rec.dest_location_id = fgwh.lot_stock_id.id
        return super(MrpProductionReturnInherit, self)._action_move_to_location()

    def _action_scrap(self):
        """BUG-8 FIX: Guard against pre-arrival scrap (overrides quality_test if not writable).
        If the incoming picking is not yet validated, goods are NOT in the warehouse.
        Redirect move destination to scrap_loc and defer actual scrap execution.
        """
        self.ensure_one()
        if self.picking_id and self.picking_id.state != 'done':
            comp_id = self.company_id.id or self.env.company.id
            scrap_loc = self.env['stock.location'].search([
                ('scrap_location', '=', True), ('company_id', '=', comp_id)
            ], limit=1) or self.env['stock.location'].search([('scrap_location', '=', True)], limit=1)
            if scrap_loc:
                matching_moves = self.picking_id.move_ids.filtered(lambda m: m.product_id == self.product_id)
                for move in matching_moves:
                    move.write({'location_dest_id': scrap_loc.id})
                    for move_line in move.move_line_ids:
                        move_line.write({'location_dest_id': scrap_loc.id})
            # Do NOT call super() — scrap is deferred to button_validate post-hook
            _logger.info(
                "Quality return %s scrap deferred until picking %s is validated.",
                self.name, self.picking_id.name
            )
            return
        # Picking already validated (or no picking): proceed normally
        return super(MrpProductionReturnInherit, self)._action_scrap()
