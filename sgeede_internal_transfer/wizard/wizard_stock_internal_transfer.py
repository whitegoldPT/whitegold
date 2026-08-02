# -*- coding: utf-8 -*-
from datetime import datetime
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_round
import logging

_logger = logging.getLogger(__name__)


class WizardStockInternalTransfer(models.TransientModel):
    _name = 'wizard.stock.internal.transfer'
    _description = 'Wizard Stock Internal Transfer'

    transfer_id = fields.Many2one('stock.internal.transfer', string="Transfer")
    item_ids = fields.One2many('stock.internal.transfer.items', 'transfer_id', string="Items")
    is_return_to_sender = fields.Boolean(string="Is Return to Sender", default=False)
    is_partial_receive = fields.Boolean(string="Is Partial Receive", default=False)
    partial_receive_message = fields.Text(string="Partial Receive Message", readonly=True)

    @api.model
    def default_get(self, fields):
        """Load default values for the wizard based on the transfer state"""
        res = super(WizardStockInternalTransfer, self).default_get(fields)
        transfer_ids = self._context.get('active_ids', [])
        active_model = self._context.get('active_model')

        if not transfer_ids or len(transfer_ids) != 1:
            return res

        if active_model != 'stock.internal.transfer':
            raise UserError(_('Bad context propagation'))

        transfer_id = transfer_ids[0]
        transfer = self.env['stock.internal.transfer'].browse(transfer_id)
        company = self.env.company

        items = []

        if not company.transit_location_id:
            raise UserError(_("Please setup your stock transit location in Setting - Internal Transfer Configuration"))

        # Check if this is a return to sender operation
        is_return_to_sender = self._context.get('return_to_sender', False)

        if is_return_to_sender:
            # Return to sender: from transit to source warehouse
            source_location_id = company.transit_location_id.id
            dest_location_id = transfer.source_warehouse_id.lot_stock_id.id
            res['is_return_to_sender'] = True

            # For return to sender, get quantities from actual transit
            for transit in transfer.transit_product_ids:
                # Get actual quantity available in transit location
                qty_in_transit = transit.product_qty

                item = {
                    'product_id': transit.product_id.id,
                    'product_uom_id': transit.product_uom_id.id,
                    'product_qty': transit.product_qty,  # Default to full transit quantity
                    'qty_available': qty_in_transit,  # Show transit quantity as available
                    'qty_in_transit': qty_in_transit,
                    'lot_id': transit.lot_id.id if transit.lot_id else False,
                    'source_location_id': source_location_id,
                    'dest_location_id': dest_location_id,
                    'line_id': False,
                    'second_uom': transit.second_uom if hasattr(transit, 'second_uom') else 1,
                    'need_second_uom': transit.need_second_uom if hasattr(transit, 'need_second_uom') else False,
                }
                items.append((0, 0, item))

        elif transfer.state == 'draft':
            # SEND LOGIC: from source to transit
            source_location_id = transfer.source_warehouse_id.lot_stock_id.id
            dest_location_id = company.transit_location_id.id

            for line in transfer.line_ids:
                # Get available quantity in source location
                qty_available = line.qty_available

                item = {
                    'product_id': line.product_id.id,
                    'product_uom_id': line.product_uom_id.id,
                    'product_qty': line.product_qty,
                    'qty_available': qty_available,  # Show source location quantity
                    'qty_in_transit': 0,  # Not in transit yet
                    'lot_id': line.lot_id.id if line.lot_id else False,
                    'source_location_id': source_location_id,
                    'dest_location_id': dest_location_id,
                    'line_id': line.id,
                    'second_uom': line.second_uom,
                    'need_second_uom': line.need_second_uom,
                }
                if line.product_id:
                    items.append((0, 0, item))

        elif transfer.state in ['send', 'partial_receive']:
            # RECEIVE LOGIC: from transit to destination
            source_location_id = company.transit_location_id.id
            dest_location_id = transfer.dest_warehouse_id.lot_stock_id.id

            # For receive, get quantities from actual transit
            for transit in transfer.transit_product_ids:
                # Get actual quantity available in transit location
                qty_in_transit = transit.product_qty

                item = {
                    'product_id': transit.product_id.id,
                    'product_uom_id': transit.product_uom_id.id,
                    'product_qty': transit.product_qty,  # Default to full transit quantity
                    'qty_available': qty_in_transit,  # Show transit quantity as available
                    'qty_in_transit': qty_in_transit,
                    'lot_id': transit.lot_id.id if transit.lot_id else False,
                    'source_location_id': source_location_id,
                    'dest_location_id': dest_location_id,
                    'line_id': False,
                    'second_uom': transit.second_uom if hasattr(transit, 'second_uom') else 1,
                    'need_second_uom': transit.need_second_uom if hasattr(transit, 'need_second_uom') else False,
                }
                items.append((0, 0, item))

        res.update(item_ids=items)
        return res

    def button_confirm(self):
        """Process the wizard confirmation for send, receive, or return operations"""
        for tf in self:
            if 'active_ids' in self._context:
                transfer = self.env['stock.internal.transfer'].browse(self._context.get('active_ids')[0])
                company = self.env.company

                # Check if this is a return to sender operation
                is_return_to_sender = self._context.get('return_to_sender', False) or tf.is_return_to_sender

                # Validate quantities before proceeding
                for wizard_line in tf.item_ids:
                    if wizard_line.product_qty < 0:
                        raise UserError(_('Quantity cannot be negative for product %s.') % wizard_line.product_id.name)

                    # Get the original transfer line
                    if wizard_line.line_id:
                        if is_return_to_sender:
                            # For return to sender, check against quantity in transit
                            max_qty = wizard_line.line_id.qty_in_transit
                        elif transfer.state in ['send', 'partial_receive']:
                            # For receive, check against quantity in transit
                            max_qty = wizard_line.line_id.qty_in_transit
                        else:
                            # For send, check against original quantity
                            max_qty = wizard_line.line_id.product_qty

                        if wizard_line.product_qty > max_qty:
                            raise UserError(
                                _('Quantity for product %s cannot exceed %s %s.')
                                % (wizard_line.product_id.name, max_qty, wizard_line.product_uom_id.name)
                            )

                if is_return_to_sender:
                    # RETURN TO SENDER LOGIC
                    if self.env.uid not in transfer.source_warehouse_id.user_ids.ids:
                        raise UserError(_('You are not authorized to return products to sender!'))

                    if transfer.state != 'partial_receive':
                        raise UserError(_('You can only return products when transfer is in Partially Received state!'))

                    # Create a return picking (incoming for sender warehouse)
                    type_obj = self.env['stock.picking.type']
                    return_type = type_obj.search([
                        ('default_location_dest_id', '=', transfer.source_warehouse_id.lot_stock_id.id),
                        ('code', '=', 'incoming')
                    ], limit=1)

                    if not return_type:
                        raise UserError(_('Unable to find return picking type for sender warehouse!'))

                    picking_obj = self.env['stock.picking']
                    return_picking = picking_obj.create({
                        'picking_type_id': return_type.id,
                        'transfer_id': transfer.id,
                        'location_id': company.transit_location_id.id,
                        'location_dest_id': transfer.source_warehouse_id.lot_stock_id.id,
                        'company_id': company.id,
                        'origin': _('Return from transfer %s') % transfer.name,
                    })

                    move_obj = self.env['stock.move']

                    for wizard_line in tf.item_ids:
                        if wizard_line.product_qty > 0:
                            _rounding = wizard_line.product_uom_id.rounding if wizard_line.product_uom_id else 0.01
                            _qty = float_round(wizard_line.product_qty, precision_rounding=_rounding)
                            move_vals = {
                                'name': _('Return to Sender: %s') % wizard_line.product_id.name,
                                'product_id': wizard_line.product_id.id,
                                'product_uom': wizard_line.product_uom_id.id,
                                'product_uom_qty': _qty,
                                'location_id': wizard_line.source_location_id.id,
                                'location_dest_id': wizard_line.dest_location_id.id,
                                'picking_id': return_picking.id,
                                'company_id': company.id,
                            }

                            # Add second UOM to move if needed
                            if hasattr(move_obj, 'second_uom') and wizard_line.need_second_uom:
                                move_vals['second_uom'] = wizard_line.second_uom

                            move_id = move_obj.create(move_vals)

                            if wizard_line.lot_id:
                                self.env['stock.move.line'].create({
                                    'move_id': move_id.id,
                                    'product_id': wizard_line.product_id.id,
                                    'product_uom_id': wizard_line.product_uom_id.id,
                                    'lot_id': wizard_line.lot_id.id,
                                    'company_id': company.id,
                                    'location_id': wizard_line.source_location_id.id,
                                    'location_dest_id': wizard_line.dest_location_id.id,
                                    'quantity': _qty,
                                })

                    picking_obj = self.env['stock.picking'].browse(return_picking.id)

                    # Confirm and assign the picking
                    picking_obj.action_confirm()
                    picking_obj.action_assign()

                    # Check if any moves couldn't be reserved BEFORE validating
                    unavailable_moves = picking_obj.move_ids.filtered(
                        lambda m: m.state in ('confirmed', 'partially_available')
                    )
                    if unavailable_moves:
                        unavailable_products = []
                        for move in unavailable_moves:
                            domain = [
                                ('product_id', '=', move.product_id.id),
                                ('location_id', '=', move.location_id.id),
                                ('quantity', '>', 0)
                            ]
                            if move.move_line_ids and move.move_line_ids.lot_id:
                                domain.append(('lot_id', 'in', move.move_line_ids.lot_id.ids))

                            # Use sudo() to bypass access restrictions
                            quants = self.env['stock.quant'].sudo().search(domain)
                            available_qty = sum(quants.mapped('quantity'))

                            unavailable_products.append(
                                _("- %s: Requested %s %s, Available %s %s") % (
                                    move.product_id.name,
                                    move.product_uom_qty,
                                    move.product_uom.name,
                                    available_qty,
                                    move.product_uom.name
                                )
                            )

                        # Don't cancel the picking, just show error
                        raise UserError(_(
                            "Cannot complete return due to insufficient stock in transit:\n%s\n\n"
                            "Please adjust quantities or ensure stock is available in transit location."
                        ) % "\n".join(unavailable_products))

                    # Validate the picking
                    try:
                        res = picking_obj.button_validate()

                        # Handle validation result safely
                        if isinstance(res, dict):
                            if res.get('res_model') == 'stock.backorder.confirmation' and res.get('res_id'):
                                backorder_wiz = self.env['stock.backorder.confirmation'].browse(res['res_id'])
                                backorder_wiz.process()
                            elif res.get('res_model') == 'stock.immediate.transfer' and res.get('res_id'):
                                immediate_wiz = self.env['stock.immediate.transfer'].browse(res['res_id'])
                                immediate_wiz.process()
                            elif res.get('res_model'):
                                _logger.warning("Unexpected validation result: %s", res)

                        # Double-check if picking was successfully done
                        if picking_obj.state != 'done':
                            raise UserError(
                                _('Failed to validate the return transfer. Picking state: %s') % picking_obj.state)

                    except Exception as e:
                        raise UserError(_('Failed to validate return transfer: %s\n\nPicking state: %s') % (
                            str(e), picking_obj.state
                        ))

                    # Log the return operation
                    transfer.message_post(body=_("Return picking %s created and validated for %s products.") % (
                        return_picking.name, len(tf.item_ids)
                    ))

                    # Refresh transit quantities after return
                    transfer._compute_transit_quantities()

                    # Check if all products are now fully processed
                    transfer._check_no_products_in_transit()

                    # Recompute total_planned_qty for all lines after return
                    transfer.line_ids._compute_total_planned_qty()

                    message = _("Products returned to sender successfully.")
                    transfer.message_post(body=message)

                elif transfer.state == 'draft':
                    # SEND LOGIC
                    backorders = []
                    user_list = []
                    user_ids = transfer.source_warehouse_id.user_ids
                    if user_ids:
                        user_list = user_ids.ids

                    if self.env.uid not in user_list:
                        raise UserError(_('You are not authorized to send products!'))

                    # Track which lines are being sent (to identify lines to delete)
                    sent_line_ids = []
                    lines_to_delete = []

                    # First pass: Process lines that are in the wizard
                    for wizard_line in tf.item_ids:
                        found = False
                        for trans in transfer.line_ids:
                            if wizard_line.product_id.id == trans.product_id.id:
                                found = True
                                sent_line_ids.append(trans.id)

                                # Check available stock in source location
                                available_qty = self.env['stock.quant']._get_available_quantity(
                                    wizard_line.product_id,
                                    wizard_line.source_location_id,
                                    strict=True
                                )
                                if available_qty < wizard_line.product_qty:
                                    raise UserError(_(
                                        'Insufficient stock for product %s. Available: %s %s, Requested: %s %s'
                                    ) % (
                                                        wizard_line.product_id.name,
                                                        available_qty,
                                                        wizard_line.product_uom_id.name,
                                                        wizard_line.product_qty,
                                                        wizard_line.product_uom_id.name
                                                    ))

                                    # if wizard_line.product_qty > trans.product_qty:
                                    #     raise UserError(_('You have exceeded the available product quantity.'))
                                    # elif wizard_line.product_qty < trans.product_qty:
                                    #     # Create backorder for remaining quantity
                                    #     backorder = {
                                    #         'product_id': wizard_line.product_id.id,
                                    #         'product_qty': trans.product_qty - wizard_line.product_qty,
                                    #         'lot_id': wizard_line.lot_id.id if wizard_line.lot_id else False,
                                    #         'product_uom_id': wizard_line.product_uom_id.id,
                                    #         'state': 'draft',
                                    #         'qty_available': wizard_line.qty_available,
                                    #     }
                                    #     backorders.append((0, 0, backorder))
                                    #
                                    #     # Update the original line with sent quantity
                                    #     trans.write({
                                    #         'product_qty': wizard_line.product_qty,
                                    #         'qty_available': wizard_line.qty_available,
                                    #     })
                                    # Trigger recomputation of total_planned_qty for all lines with same product
                                    transfer.line_ids.filtered(
                                        lambda l: l.product_id.id == wizard_line.product_id.id
                                    )._compute_total_planned_qty()
                                else:
                                    # Full quantity sent, just update available quantity
                                    trans.write({
                                        'qty_available': wizard_line.qty_available,
                                    })
                                    # Trigger recomputation of total_planned_qty for all lines with same product
                                    transfer.line_ids.filtered(
                                        lambda l: l.product_id.id == wizard_line.product_id.id
                                    )._compute_total_planned_qty()
                                break

                        # If product not found in original transfer (should not happen, but just in case)
                        if not found and wizard_line.product_qty > 0:
                            # Create new line if product was added in wizard
                            new_line = self.env['stock.internal.transfer.line'].create({
                                'transfer_id': transfer.id,
                                'product_id': wizard_line.product_id.id,
                                'product_qty': wizard_line.product_qty,
                                'product_uom_id': wizard_line.product_uom_id.id,
                                'lot_id': wizard_line.lot_id.id if wizard_line.lot_id else False,
                                'state': 'draft',
                                'qty_available': wizard_line.qty_available,
                                'second_uom': wizard_line.second_uom,
                                'need_second_uom': wizard_line.need_second_uom,
                            })
                            sent_line_ids.append(new_line.id)
                            # Trigger recomputation of total_planned_qty for all lines with same product
                            transfer.line_ids.filtered(
                                lambda l: l.product_id.id == wizard_line.product_id.id
                            )._compute_total_planned_qty()

                    # Identify lines to delete (lines not in wizard with quantity 0)
                    for line in transfer.line_ids:
                        if line.id not in sent_line_ids:
                            lines_to_delete.append(line.id)

                    # Delete lines that were removed from wizard
                    if lines_to_delete:
                        # Get product IDs of lines being deleted to recompute totals
                        deleted_lines = self.env['stock.internal.transfer.line'].browse(lines_to_delete)
                        affected_products = deleted_lines.mapped('product_id')
                        deleted_lines.unlink()
                        # Trigger recomputation of total_planned_qty for affected products
                        for product in affected_products:
                            transfer.line_ids.filtered(
                                lambda l: l.product_id.id == product.id
                            )._compute_total_planned_qty()
                        message = _("Removed %s product(s) from transfer.") % len(lines_to_delete)
                        transfer.message_post(body=message)

                    # Create backorder transfer if needed
                    if backorders:
                        backorder_transfer = self.env['stock.internal.transfer'].create({
                            'date': fields.Datetime.now(),
                            'source_warehouse_id': transfer.source_warehouse_id.id,
                            'dest_warehouse_id': transfer.dest_warehouse_id.id,
                            'backorder_id': self._context.get('active_ids')[0],
                            'source_document': transfer.name,
                            'state': 'draft',
                            'line_ids': backorders,
                        })
                        message = _("Backorder %s created for remaining quantities.") % backorder_transfer.name
                        transfer.message_post(body=message)

                    # Create picking
                    type_obj = self.env['stock.picking.type']
                    types = type_obj.search([
                        ('default_location_src_id', '=', transfer.source_warehouse_id.lot_stock_id.id),
                        ('code', '=', 'outgoing')
                    ], limit=1)

                    if not types:
                        raise UserError(_('Unable to find source location in Stock Picking'))

                    picking_obj = self.env['stock.picking']
                    picking_id = picking_obj.create({
                        'picking_type_id': types.id,
                        'transfer_id': self._context.get('active_ids')[0],
                        'location_id': transfer.source_warehouse_id.lot_stock_id.id,
                        'location_dest_id': company.transit_location_id.id,
                        'company_id': company.id,
                        'send_picking': True,
                        'origin': transfer.source_document or transfer.name,
                    })

                    move_obj = self.env['stock.move']

                    for wizard_line in tf.item_ids:
                        if wizard_line.product_qty > 0:
                            _rounding = wizard_line.product_uom_id.rounding if wizard_line.product_uom_id else 0.01
                            _qty = float_round(wizard_line.product_qty, precision_rounding=_rounding)
                            move_vals = {
                                'name': 'Stock Internal Transfer',
                                'product_id': wizard_line.product_id.id,
                                'product_uom': wizard_line.product_uom_id.id,
                                'product_uom_qty': _qty,
                                'location_id': wizard_line.source_location_id.id,
                                'location_dest_id': wizard_line.dest_location_id.id,
                                'picking_id': picking_id.id,
                                'company_id': company.id,
                            }

                            # Add second UOM to move if needed
                            if hasattr(move_obj, 'second_uom') and wizard_line.need_second_uom:
                                move_vals['second_uom'] = wizard_line.second_uom

                            move_obj.create(move_vals)

                    picking_obj = self.env['stock.picking'].browse(picking_id.id)

                    # Confirm and assign the picking
                    picking_obj.action_confirm()
                    picking_obj.action_assign()

                    # Check if any moves couldn't be reserved BEFORE validating
                    unavailable_moves = picking_obj.move_ids.filtered(
                        lambda m: m.state in ('confirmed', 'partially_available')
                    )
                    if unavailable_moves:
                        unavailable_products = []
                        for move in unavailable_moves:
                            # Get available quantity from quants
                            domain = [
                                ('product_id', '=', move.product_id.id),
                                ('location_id', '=', move.location_id.id),
                                ('quantity', '>', 0)
                            ]
                            # Use sudo() to bypass access restrictions for send operation too
                            quants = self.env['stock.quant'].sudo().search(domain)
                            available_qty = sum(quants.mapped('quantity'))

                            unavailable_products.append(
                                _("- %s: Requested %s %s, Available %s %s") % (
                                    move.product_id.name,
                                    move.product_uom_qty,
                                    move.product_uom.name,
                                    available_qty,
                                    move.product_uom.name
                                )
                            )

                        # Don't cancel the picking, just show error
                        raise UserError(_(
                            "Cannot complete transfer due to insufficient stock:\n%s\n\n"
                            "Please adjust quantities or ensure stock is available."
                        ) % "\n".join(unavailable_products))

                    # Validate the picking
                    try:
                        res = picking_obj.button_validate()

                        # Handle validation result safely
                        if isinstance(res, dict):
                            if res.get('res_model') == 'stock.backorder.confirmation' and res.get('res_id'):
                                backorder_wiz = self.env['stock.backorder.confirmation'].browse(res['res_id'])
                                backorder_wiz.process()
                            elif res.get('res_model') == 'stock.immediate.transfer' and res.get('res_id'):
                                immediate_wiz = self.env['stock.immediate.transfer'].browse(res['res_id'])
                                immediate_wiz.process()
                            elif res.get('res_model'):
                                _logger.warning("Unexpected validation result: %s", res)

                        # Double-check if picking was successfully done
                        if picking_obj.state != 'done':
                            raise UserError(_('Failed to validate the transfer. Picking state: %s') % picking_obj.state)

                    except Exception as e:
                        raise UserError(
                            _('Failed to validate transfer: %s\n\nPicking state: %s') % (str(e), picking_obj.state))

                    transfer.state = 'send'
                    message = _("Transfer sent successfully. Created picking: %s") % picking_id.name
                    transfer.message_post(body=message)

                    # Recompute total_planned_qty for all lines after changes
                    transfer.line_ids._compute_total_planned_qty()

                elif transfer.state in ['send', 'partial_receive']:
                    # RECEIVE LOGIC - Use actual transit quantities
                    # Check if this is a partial receive
                    is_partial_receive = False
                    deleted_lines_info = []

                    # Create mapping of available transit quantities
                    transit_quantities = {}
                    for transit in transfer.transit_product_ids:
                        key = (transit.product_id.id, transit.lot_id.id if transit.lot_id else False)
                        transit_quantities[key] = transit.product_qty

                    # Get all transit keys
                    all_transit_keys = set(transit_quantities.keys())

                    # Get wizard keys (products being received)
                    wizard_keys = set()
                    for wizard_line in tf.item_ids:
                        key = (wizard_line.product_id.id, wizard_line.lot_id.id if wizard_line.lot_id else False)
                        wizard_keys.add(key)

                        if key in transit_quantities:
                            available_in_transit = transit_quantities[key]

                            if wizard_line.product_qty > available_in_transit:
                                raise UserError(_(
                                    'Cannot receive %s %s of %s. Only %s %s available in transit.'
                                ) % (
                                                    wizard_line.product_qty,
                                                    wizard_line.product_uom_id.name,
                                                    wizard_line.product_id.name,
                                                    available_in_transit,
                                                    wizard_line.product_uom_id.name
                                                ))

                            if wizard_line.product_qty < available_in_transit:
                                is_partial_receive = True
                        else:
                            # This shouldn't happen as wizard should only show transit products
                            is_partial_receive = True

                    # Check for transit products not in wizard (deleted lines)
                    missing_keys = all_transit_keys - wizard_keys
                    if missing_keys:
                        is_partial_receive = True
                        for key in missing_keys:
                            product_id, lot_id = key
                            product = self.env['product.product'].browse(product_id)
                            lot = self.env['stock.lot'].browse(lot_id) if lot_id else False
                            deleted_lines_info.append(
                                _("- Product: %s, Lot: %s, Quantity in transit: %s") % (
                                    product.name,
                                    lot.name if lot else _('No Lot'),
                                    transit_quantities[key]
                                )
                            )

                    # Check authorization
                    user_list = []
                    user_ids = transfer.dest_warehouse_id.user_ids
                    if user_ids:
                        user_list = user_ids.ids

                    if self.env.uid not in user_list:
                        raise UserError(_('You are not authorized to receive products!'))

                    # Check available quantities in transit location BEFORE creating picking
                    for wizard_line in tf.item_ids:
                        # Check available stock in transit location - use sudo() to bypass access rules
                        domain = [
                            ('product_id', '=', wizard_line.product_id.id),
                            ('location_id', '=', wizard_line.source_location_id.id),
                            ('quantity', '>', 0)
                        ]
                        if wizard_line.lot_id:
                            domain.append(('lot_id', '=', wizard_line.lot_id.id))

                        # Use sudo() to bypass access restrictions
                        quants = self.env['stock.quant'].sudo().search(domain)
                        available_qty = sum(quants.mapped('quantity'))

                        if available_qty < wizard_line.product_qty:
                            raise UserError(_(
                                'Insufficient stock in transit for product %s. Available: %s %s, Requested: %s %s'
                            ) % (
                                                wizard_line.product_id.name,
                                                available_qty,
                                                wizard_line.product_uom_id.name,
                                                wizard_line.product_qty,
                                                wizard_line.product_uom_id.name
                                            ))

                    type_obj = self.env['stock.picking.type']
                    types = type_obj.search([
                        ('default_location_dest_id', '=', transfer.dest_warehouse_id.lot_stock_id.id),
                        ('code', '=', 'incoming')
                    ], limit=1)

                    if not types:
                        raise UserError(_('Unable to find destination location in Stock Picking'))

                    picking_obj = self.env['stock.picking']
                    picking_id = picking_obj.create({
                        'picking_type_id': types.id,
                        'transfer_id': self._context.get('active_ids')[0],
                        'location_id': company.transit_location_id.id,
                        'location_dest_id': transfer.dest_warehouse_id.lot_stock_id.id,
                        'company_id': company.id,
                        'origin': transfer.source_document or transfer.name,
                    })

                    move_obj = self.env['stock.move']

                    for wizard_line in tf.item_ids:
                        if wizard_line.product_qty > 0:
                            _rounding = wizard_line.product_uom_id.rounding if wizard_line.product_uom_id else 0.01
                            _qty = float_round(wizard_line.product_qty, precision_rounding=_rounding)
                            move_vals = {
                                'name': 'Receive from Internal Transfer',
                                'product_id': wizard_line.product_id.id,
                                'product_uom': wizard_line.product_uom_id.id,
                                'product_uom_qty': _qty,
                                'location_id': wizard_line.source_location_id.id,
                                'location_dest_id': wizard_line.dest_location_id.id,
                                'picking_id': picking_id.id,
                                'company_id': company.id,
                            }

                            # Add second UOM to move if needed
                            if hasattr(move_obj, 'second_uom') and wizard_line.need_second_uom:
                                move_vals['second_uom'] = wizard_line.second_uom

                            move_id = move_obj.create(move_vals)

                            if wizard_line.lot_id:
                                self.env['stock.move.line'].create({
                                    'move_id': move_id.id,
                                    'product_id': wizard_line.product_id.id,
                                    'product_uom_id': wizard_line.product_uom_id.id,
                                    'lot_id': wizard_line.lot_id.id,
                                    'company_id': company.id,
                                    'location_id': wizard_line.source_location_id.id,
                                    'location_dest_id': wizard_line.dest_location_id.id,
                                    'quantity': _qty,
                                })

                    picking_obj = self.env['stock.picking'].browse(picking_id.id)

                    # Confirm and assign the picking
                    picking_obj.action_confirm()
                    picking_obj.action_assign()

                    # Check if any moves couldn't be reserved (for transit to destination) BEFORE validating
                    unavailable_moves = picking_obj.move_ids.filtered(
                        lambda m: m.state in ('confirmed', 'partially_available')
                    )
                    if unavailable_moves:
                        unavailable_products = []
                        for move in unavailable_moves:
                            domain = [
                                ('product_id', '=', move.product_id.id),
                                ('location_id', '=', move.location_id.id),
                                ('quantity', '>', 0)
                            ]
                            if move.move_line_ids and move.move_line_ids.lot_id:
                                domain.append(('lot_id', 'in', move.move_line_ids.lot_id.ids))

                            # Use sudo() to bypass access restrictions
                            quants = self.env['stock.quant'].sudo().search(domain)
                            available_qty = sum(quants.mapped('quantity'))

                            unavailable_products.append(
                                _("- %s: Requested %s %s, Available %s %s") % (
                                    move.product_id.name,
                                    move.product_uom_qty,
                                    move.product_uom.name,
                                    available_qty,
                                    move.product_uom.name
                                )
                            )

                        # Don't cancel the picking, just show error
                        raise UserError(_(
                            "Cannot complete receive transfer due to insufficient stock in transit:\n%s\n\n"
                            "Please adjust quantities or ensure stock is available in transit location."
                        ) % "\n".join(unavailable_products))

                    # Validate the picking
                    try:
                        res = picking_obj.button_validate()

                        # Handle validation result safely
                        if isinstance(res, dict):
                            if res.get('res_model') == 'stock.backorder.confirmation' and res.get('res_id'):
                                backorder_wiz = self.env['stock.backorder.confirmation'].browse(res['res_id'])
                                backorder_wiz.process()
                            elif res.get('res_model') == 'stock.immediate.transfer' and res.get('res_id'):
                                immediate_wiz = self.env['stock.immediate.transfer'].browse(res['res_id'])
                                immediate_wiz.process()
                            elif res.get('res_model'):
                                _logger.warning("Unexpected validation result: %s", res)

                        # Double-check if picking was successfully done
                        if picking_obj.state != 'done':
                            raise UserError(
                                _('Failed to validate the receive transfer. Picking state: %s') % picking_obj.state)

                    except Exception as e:
                        raise UserError(_('Failed to validate receive transfer: %s\n\nPicking state: %s') % (str(e),
                                                                                                             picking_obj.state))

                    # Log the receive operation
                    transfer.message_post(body=_("Receive picking %s created and validated for %s products.") % (
                        picking_id.name, len(tf.item_ids)
                    ))

                    # Refresh transit quantities after receive
                    transfer._compute_transit_quantities()

                    # qty_received is a computed field that automatically calculates from pickings
                    # No need to manually update it - it will be recalculated automatically
                    # Trigger recomputation to ensure it's up to date
                    transfer.line_ids._compute_qty_received()

                    # Post picking message
                    message = _("Receive picking created: %s") % picking_id.name
                    transfer.message_post(body=message)

                    # Check if ALL transit products were fully received
                    all_transit_products_received = True

                    # First, update received quantities for products in the wizard
                    received_products = {}
                    for wizard_line in tf.item_ids:
                        key = (wizard_line.product_id.id, wizard_line.lot_id.id if wizard_line.lot_id else False)
                        if key in transit_quantities:
                            received_products[key] = wizard_line.product_qty

                    # Now check if ALL transit products were fully received
                    for key, transit_qty in transit_quantities.items():
                        received_qty = received_products.get(key, 0)
                        if received_qty < transit_qty:
                            all_transit_products_received = False
                            break

                    # Recompute total_planned_qty for all lines after receive
                    transfer.line_ids._compute_total_planned_qty()

                    if all_transit_products_received:
                        # All products in transit were fully received
                        transfer.state = 'receive'
                        message = _("All products received successfully.")
                        transfer.message_post(body=message)
                    else:
                        # Some products were not fully received
                        transfer.state = 'partial_receive'
                        message = _("Products partially received. Transfer set to Partially Received.")

                        # Add info about deleted lines if any
                        if deleted_lines_info:
                            message += "\n\n" + _("Products not received (deleted from wizard):") + "\n"
                            message += "\n".join(deleted_lines_info)

                        transfer.message_post(body=message)

                        # Show partial receive reason wizard
                        if is_partial_receive:
                            # Store deleted lines info in context to pass to wizard
                            ctx = self._context.copy()
                            ctx.update({
                                'deleted_lines_info': deleted_lines_info
                            })

                            return {
                                'name': _('Partial Receive Reason'),
                                'type': 'ir.actions.act_window',
                                'view_mode': 'form',
                                'res_model': 'partial.receive.reason.wizard',
                                'view_id': self.env.ref(
                                    'sgeede_internal_transfer.partial_receive_reason_wizard_view').id,
                                'target': 'new',
                                'context': {
                                    'default_transfer_id': transfer.id,
                                    'deleted_lines_info': deleted_lines_info,
                                }
                            }

        return True

    def wizard_view(self, created_id):
        """Return the wizard view with appropriate title based on operation"""
        view_id = self.env.ref('sgeede_internal_transfer.wizard_stock_internal_transfer_view').id

        # Determine wizard title based on context
        title = _('Enter Transfer Details')
        if self._context.get('return_to_sender'):
            title = _('Return Products to Sender')
        elif self.transfer_id:
            if self.transfer_id.state == 'draft':
                title = _('Send Products')
            elif self.transfer_id.state in ['send', 'partial_receive']:
                title = _('Receive Products')

        return {
            'name': title,
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'wizard.stock.internal.transfer',
            'views': [(view_id, 'form')],
            'view_id': view_id,
            'target': 'new',
            'res_id': created_id,
            'context': self.env.context
        }


class StockInternalTransferItems(models.TransientModel):
    _name = "stock.internal.transfer.items"
    _description = "Stock Internal Transfer Items"

    lot_id = fields.Many2one('stock.lot', string="Lot")
    transfer_id = fields.Many2one('wizard.stock.internal.transfer', string="Transfer")
    product_id = fields.Many2one('product.product', string="Product")
    product_qty = fields.Float(string="Quantity")
    qty_available = fields.Float(string="Available in Source", readonly=True)
    qty_in_transit = fields.Float(string="Available in Transit", readonly=True)
    product_uom_id = fields.Many2one('uom.uom', string="Unit of Measure")
    source_location_id = fields.Many2one('stock.location', string="Source Location")
    transit_location_id = fields.Many2one('stock.location', string="Transit Location")
    dest_location_id = fields.Many2one('stock.location', string="Destination Location")
    line_id = fields.Many2one('stock.internal.transfer.line', string="Transfer Line")
    # NEW: Add second UOM fields to wizard items
    second_uom = fields.Integer(
        string='Second UOM',
        default=1,
        tracking=True,
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
        for record in self:
            if record.product_id:
                # Try to access need_second_uom on product, but handle gracefully if it doesn't exist
                try:
                    record.need_second_uom = record.product_id.need_second_uom
                except Exception:
                    # If field doesn't exist on product, default to False
                    record.need_second_uom = False
            else:
                record.need_second_uom = False

    @api.onchange('product_id')
    def product_id_change(self):
        """Set product UoM when product changes"""
        if not self.product_id:
            self.product_uom_id = False
            self.need_second_uom = False
            self.second_uom = 1
        else:
            self.product_uom_id = self.product_id.uom_id
            # Compute need_second_uom
            try:
                self.need_second_uom = self.product_id.need_second_uom
            except Exception:
                self.need_second_uom = False
            # Set default second_uom to 1
            self.second_uom = 1

    @api.constrains('product_qty')
    def _check_product_qty(self):
        """Validate that quantity doesn't exceed available quantity"""
        for record in self:
            if record.product_qty < 0:
                raise ValidationError(_('Quantity cannot be negative.'))

            # Get the original transfer line
            if record.line_id:
                if record.transfer_id.is_return_to_sender:
                    max_qty = record.line_id.qty_in_transit
                else:
                    max_qty = record.line_id.product_qty

                if record.product_qty > max_qty:
                    raise ValidationError(
                        _('Cannot exceed %s %s.')
                        % (max_qty, record.line_id.product_uom_id.name)
                    )