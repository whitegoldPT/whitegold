# custom_pug/sgeede_internal_transfer/models/stock_internal_transfer.py
# -*- coding: utf-8 -*-
import json
import time
import logging
from datetime import date, datetime
from dateutil import relativedelta
from odoo import fields, models, api, SUPERUSER_ID, _
from odoo.tools import float_compare, float_round
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT, DEFAULT_SERVER_DATE_FORMAT
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class StockInternalTransfer(models.Model):
    _name = 'stock.internal.transfer'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Stock Internal Transfer'
    _order = 'date desc, id desc'

    def action_cancel(self):
        # Restrict cancel action to admin users only
        if not self.env.user.has_group('base.group_system'):
            raise UserError(_("Only administrators can cancel transfers."))
        self.write({'state': 'cancel'})
        message = _("Transfer was cancelled by %s.") % self.env.user.name
        self.message_post(body=message)
        return True

    def action_draft(self):
        self.write({'state': 'draft'})
        message = _("Transfer was set to draft by %s.") % self.env.user.name
        self.message_post(body=message)
        return True

    def action_send(self):
        self.write({'state': 'send'})
        message = _("Transfer was sent by %s.") % self.env.user.name
        self.message_post(body=message)
        return True

    def action_receive(self):
        self.write({'state': 'done'})
        message = _("Transfer was received by %s.") % self.env.user.name
        self.message_post(body=message)
        return True

    def action_partial_receive(self):
        self.write({'state': 'partial_receive'})
        message = _("Transfer was partially received by %s.") % self.env.user.name
        self.message_post(body=message)
        return True

    def action_return_to_sender(self):
        """Open wizard to return remaining products to sender"""
        ctx = dict(self._context)
        ctx.update({
            'active_model': self._name,
            'active_ids': self.ids,
            'active_id': self.ids[0] if self.ids else False,
            'return_to_sender': True,
        })

        created_id = self.env['wizard.stock.internal.transfer'].with_context(ctx).create({
            'transfer_id': self.ids[0] if self.ids else False
        }).id
        return self.env['wizard.stock.internal.transfer'].with_context(ctx).wizard_view(created_id)

    def do_enter_wizard(self):
        """Check access rights before opening wizard"""
        self.ensure_one()

        # Check access rights
        if self.state == 'draft':
            if self.env.uid not in self.source_warehouse_id.user_ids.ids:
                raise UserError(_('You are not authorized to send products from this warehouse!'))
        elif self.state in ['send', 'partial_receive']:
            if self.env.uid not in self.dest_warehouse_id.user_ids.ids:
                raise UserError(_('You are not authorized to receive products to this warehouse!'))

        ctx = dict(self._context)
        ctx.update({
            'active_model': self._name,
            'active_ids': self.ids,
            'active_id': self.ids[0] if self.ids else False
        })

        created_id = self.env['wizard.stock.internal.transfer'].with_context(ctx).create({
            'transfer_id': self.ids[0] if self.ids else False
        }).id
        return self.env['wizard.stock.internal.transfer'].with_context(ctx).wizard_view(created_id)

    def _check_no_products_in_transit(self):
        """Check if there are no products in transit and update state accordingly"""
        self.ensure_one()
        if not self.transit_product_ids and self.state in ['partial_receive', 'send']:
            # Check if all lines are fully processed using float_compare to avoid float == float
            all_processed = all(
                float_compare(
                    line.qty_sent,
                    line.qty_received,
                    precision_rounding=line.product_uom_id.rounding if line.product_uom_id else 0.01
                ) == 0
                for line in self.line_ids if line.product_qty > 0
            )
            if all_processed:
                self.state = 'receive'
                message = _(
                    "All products have been processed (received or returned to sender). Transfer marked as received.")
                self.message_post(body=message)
                return True
        return False

    name = fields.Char(
        string='Reference',
        tracking=True,
        copy=False,
        default=lambda self: self.env['ir.sequence'].next_by_code('stock.internal.transfer') or ''
    )
    date = fields.Datetime(
        string='Date',
        tracking=True,
        default=lambda self: fields.Datetime.now()
    )
    source_warehouse_id = fields.Many2one(
        'stock.warehouse',
        string="Source Warehouse",
        tracking=True
    )
    dest_warehouse_id = fields.Many2one(
        'stock.warehouse',
        string="Destination Warehouse",
        tracking=True
    )
    state = fields.Selection(
        [
            ('cancel', 'Cancelled'),
            ('draft', 'Draft'),
            ('send', 'Sent'),
            ('partial_receive', 'Partially Received'),
            ('receive', 'Received'),
            ('done', 'Done')
        ],
        string="Status",
        tracking=True,
        default="draft",
        group_expand='_expand_states'
    )
    line_ids = fields.One2many(
        'stock.internal.transfer.line',
        'transfer_id',
        string="Transfer Lines",
        context={'is_draft_state': True}
    )
    picking_ids = fields.One2many(
        'stock.picking',
        'transfer_id',
        string="Pickings"
    )
    backorder_id = fields.Many2one(
        'stock.internal.transfer',
        string='Backorder',
        copy=False,
    )
    return_transfer_id = fields.Many2one(
        'stock.internal.transfer',
        string='Return Transfer'
    )
    requisition_id = fields.Many2one(
        'material.purchase.requisition',
        string='Purchase Requisition',
        help="Purchase Requisition that created this transfer"
    )
    source_document = fields.Char(
        string='Source Document',
        tracking=True,
        help="Document that created this transfer",
        compute='_compute_source_document',
        store=True,
    )

    @api.depends('requisition_id')
    def _compute_source_document(self):
        for record in self:
            # If explicitly being set via context (from request_stock), skip recomputation
            # for THIS record only — check inline so we don't abort the whole batch.
            if self.env.context.get('skip_compute_source_document') and not record.requisition_id:
                continue

            current_source_document = record.source_document or ''
            if not record.requisition_id:
                # Preserve any previously stored value (e.g. after requisition deletion)
                if not current_source_document:
                    record.source_document = ''
            else:
                try:
                    requisition_code = record.requisition_id.name
                    record.source_document = requisition_code or ''
                except (AttributeError, ValueError, Exception) as e:
                    # Requisition may have been deleted — preserve stored value if available
                    if current_source_document:
                        record.source_document = current_source_document
                    else:
                        record.source_document = ''
                    _logger.warning(
                        "_compute_source_document: Error accessing requisition name "
                        "for transfer ID=%s: %s", record.id, str(e))

    partial_receive_reason = fields.Text(
        string='Partial Receive Reason',
        tracking=True,
        help="Reason for partial receive"
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        index=True,
        default=lambda self: self.env.company
    )
    has_transit_products = fields.Boolean(
        string='Has Products in Transit',
        compute='_compute_has_transit_products',
        store=True
    )
    transit_product_ids = fields.One2many(
        'stock.transit.quantity',
        'transfer_id',
        string='Transit Quantities',
        readonly=True
    )
    show_send_button = fields.Boolean(
        compute='_compute_show_buttons',
        string='Show Send Button'
    )
    show_receive_button = fields.Boolean(
        compute='_compute_show_buttons',
        string='Show Receive Button'
    )
    has_requisition = fields.Boolean(
        compute='_compute_has_requisition',
        store=False,
        string='Has Requisition',
        help="Check if requisition exists and is not deleted"
    )

    def _compute_show_buttons(self):
        """Compute which buttons should be visible to current user"""
        for record in self:
            record.show_send_button = self.env.uid in record.source_warehouse_id.user_ids.ids
            record.show_receive_button = self.env.uid in record.dest_warehouse_id.user_ids.ids

    def _compute_has_requisition(self):
        """Compute if requisition exists and is accessible"""
        for record in self:
            try:
                # Use sudo() to bypass access rules — we only need to check existence, not content.
                # This avoids raw SQL while still working around potential ACL restrictions.
                if not record.id:
                    record.has_requisition = bool(record.requisition_id)
                    continue
                req = record.sudo().requisition_id
                if req:
                    # Verify the record genuinely exists (handles stale Many2one references)
                    record.has_requisition = req.exists() and bool(req.id)
                else:
                    record.has_requisition = False
            except Exception:
                record.has_requisition = False

    def _compute_transit_quantities(self):
        """Compute actual quantities in transit from completed outgoing pickings"""
        # Run as SUPERUSER to bypass permission restrictions
        TransitQuantity = self.env['stock.transit.quantity'].sudo()

        for transfer in self:
            # Delete existing transit records for this transfer
            existing_records = TransitQuantity.search([('transfer_id', '=', transfer.id)])
            existing_records.unlink()

            # Get the sending picking (outgoing to transit)
            # Use sudo() to ensure we can see all pickings regardless of rules
            transfer_sudo = transfer.sudo()
            send_picking = transfer_sudo.picking_ids.filtered(
                lambda p: p.location_dest_id == transfer.company_id.transit_location_id and p.state == 'done'
            )

            if send_picking:
                # Get all moves from sending picking
                for move in send_picking.move_ids:
                    if move.state == 'done' and move.product_uom_qty > 0:
                        # UoM rounding to eliminate floating-point imprecision
                        _rounding = move.product_uom.rounding if move.product_uom else 0.01

                        # Calculate total quantity done for this move
                        quantity_done = float_round(
                            sum(move.move_line_ids.mapped('quantity')),
                            precision_rounding=_rounding
                        )

                        # Calculate how much has been received by destination
                        received_by_dest_qty = 0.0
                        # Find receive pickings for this product (transit → destination)
                        receive_pickings = transfer_sudo.picking_ids.filtered(
                            lambda p: p.location_id == transfer.company_id.transit_location_id
                                      and p.location_dest_id == transfer.dest_warehouse_id.lot_stock_id
                                      and p.state == 'done'
                        )

                        for rec_picking in receive_pickings:
                            for rec_move in rec_picking.move_ids:
                                if rec_move.product_id.id == move.product_id.id and rec_move.state == 'done':
                                    # Check lot matching if lots are involved
                                    if move.move_line_ids.lot_id and rec_move.move_line_ids.lot_id:
                                        # If both have lots, match by lot
                                        for lot in move.move_line_ids.lot_id:
                                            matching_rec_move_lines = rec_move.move_line_ids.filtered(
                                                lambda ml: ml.lot_id.id == lot.id
                                            )
                                            if matching_rec_move_lines:
                                                received_by_dest_qty += sum(matching_rec_move_lines.mapped('quantity'))
                                    else:
                                        # No lots or mixed, sum all done quantities
                                        received_by_dest_qty += sum(rec_move.move_line_ids.mapped('quantity'))
                        received_by_dest_qty = float_round(received_by_dest_qty, precision_rounding=_rounding)

                        # Calculate how much has been returned to sender
                        returned_to_sender_qty = 0.0
                        # Find return pickings for this product (transit → source)
                        return_pickings = transfer_sudo.picking_ids.filtered(
                            lambda p: p.location_id == transfer.company_id.transit_location_id
                                      and p.location_dest_id == transfer.source_warehouse_id.lot_stock_id
                                      and p.state == 'done'
                        )

                        for ret_picking in return_pickings:
                            for ret_move in ret_picking.move_ids:
                                if ret_move.product_id.id == move.product_id.id and ret_move.state == 'done':
                                    # Check lot matching if lots are involved
                                    if move.move_line_ids.lot_id and ret_move.move_line_ids.lot_id:
                                        # If both have lots, match by lot
                                        for lot in move.move_line_ids.lot_id:
                                            matching_ret_move_lines = ret_move.move_line_ids.filtered(
                                                lambda ml: ml.lot_id.id == lot.id
                                            )
                                            if matching_ret_move_lines:
                                                returned_to_sender_qty += sum(
                                                    matching_ret_move_lines.mapped('quantity'))
                                    else:
                                        # No lots or mixed, sum all done quantities
                                        returned_to_sender_qty += sum(ret_move.move_line_ids.mapped('quantity'))
                        returned_to_sender_qty = float_round(returned_to_sender_qty, precision_rounding=_rounding)

                        # Calculate remaining in transit (sent minus received minus returned)
                        # Round the final result to avoid accumulated floating-point error
                        transit_qty = float_round(
                            quantity_done - received_by_dest_qty - returned_to_sender_qty,
                            precision_rounding=_rounding
                        )
                        if transit_qty > 0:
                            # Handle lots
                            if move.move_line_ids.lot_id:
                                for lot in move.move_line_ids.lot_id:
                                    # Calculate quantity for this specific lot (with rounding)
                                    lot_qty_done = float_round(
                                        sum(
                                            move.move_line_ids.filtered(
                                                lambda ml: ml.lot_id.id == lot.id
                                            ).mapped('quantity')
                                        ),
                                        precision_rounding=_rounding
                                    )

                                    # Calculate received by destination for this lot (with rounding)
                                    lot_received_by_dest = 0.0
                                    for rec_picking in receive_pickings:
                                        for rec_move in rec_picking.move_ids:
                                            if rec_move.product_id.id == move.product_id.id:
                                                lot_move_lines = rec_move.move_line_ids.filtered(
                                                    lambda ml: ml.lot_id.id == lot.id
                                                )
                                                if lot_move_lines:
                                                    lot_received_by_dest += sum(lot_move_lines.mapped('quantity'))
                                    lot_received_by_dest = float_round(
                                        lot_received_by_dest, precision_rounding=_rounding
                                    )

                                    # Calculate returned to sender for this lot (with rounding)
                                    lot_returned_to_sender = 0.0
                                    for ret_picking in return_pickings:
                                        for ret_move in ret_picking.move_ids:
                                            if ret_move.product_id.id == move.product_id.id:
                                                lot_ret_move_lines = ret_move.move_line_ids.filtered(
                                                    lambda ml: ml.lot_id.id == lot.id
                                                )
                                                if lot_ret_move_lines:
                                                    lot_returned_to_sender += sum(
                                                        lot_ret_move_lines.mapped('quantity'))
                                    lot_returned_to_sender = float_round(
                                        lot_returned_to_sender, precision_rounding=_rounding
                                    )

                                    # Round the final lot transit qty to eliminate accumulated FP error
                                    lot_transit_qty = float_round(
                                        lot_qty_done - lot_received_by_dest - lot_returned_to_sender,
                                        precision_rounding=_rounding
                                    )

                                    if lot_transit_qty > 0:
                                        TransitQuantity.create({
                                            'transfer_id': transfer.id,
                                            'product_id': move.product_id.id,
                                            'product_qty': lot_transit_qty,
                                            'product_uom_id': move.product_uom.id,
                                            'second_uom': move.second_uom if hasattr(move, 'second_uom') else 1,
                                            'lot_id': lot.id,
                                            'send_picking_id': send_picking[:1].id,
                                            'move_id': move.id,
                                        })
                            else:
                                # No lots
                                TransitQuantity.create({
                                    'transfer_id': transfer.id,
                                    'product_id': move.product_id.id,
                                    'product_qty': transit_qty,
                                    'product_uom_id': move.product_uom.id,
                                    'second_uom': move.second_uom if hasattr(move, 'second_uom') else 1,
                                    'lot_id': False,
                                    'send_picking_id': send_picking[:1].id,
                                    'move_id': move.id,
                                })

            # Check if no products in transit after update
            transfer._check_no_products_in_transit()

    @api.depends('transit_product_ids')
    def _compute_has_transit_products(self):
        for record in self:
            record.has_transit_products = bool(record.sudo().transit_product_ids)

    def _expand_states(self, states, domain, order):
        return [key for key, val in type(self).state.selection]

    @api.constrains('source_warehouse_id', 'dest_warehouse_id')
    def check_warehouse(self):
        for record in self:
            if record.source_warehouse_id.id == record.dest_warehouse_id.id:
                raise ValidationError(_('Source warehouse must be different from destination warehouse'))

    def get_available_transit_quantity(self, product_id, lot_id=False):
        """Get available quantity of a product in transit"""
        self.ensure_one()
        transit_qty = 0

        for transit in self.transit_product_ids:
            if transit.product_id.id == product_id:
                if lot_id:
                    if transit.lot_id and transit.lot_id.id == lot_id:
                        transit_qty += transit.product_qty
                else:
                    transit_qty += transit.product_qty

        return transit_qty

    @api.model
    def create(self, vals):
        """Override create to log in chatter"""
        transfer = super(StockInternalTransfer, self).create(vals)
        # Explicitly persist source_document at creation time if requisition_id is set.
        # This ensures the value survives even if the requisition record is later deleted.
        if transfer.requisition_id:
            try:
                requisition_code = transfer.requisition_id.name
                transfer.with_context(skip_compute_source_document=True).write(
                    {'source_document': requisition_code or ''})
            except Exception as e:
                _logger.warning(
                    "create: Could not set source_document from requisition_id: %s", str(e))

        transfer.message_post(body=_("Transfer created by %s.") % self.env.user.name)
        return transfer

    def write(self, vals):
        """Override write to log important changes in chatter"""
        if 'state' in vals:
            for record in self:
                old_state = dict(self.fields_get(allfields=['state'])['state']['selection']).get(
                    record.state, record.state)
                new_state = dict(self.fields_get(allfields=['state'])['state']['selection']).get(
                    vals['state'], vals['state'])
                if old_state != new_state:
                    record.message_post(
                        body=_("State changed from %s to %s by %s.") % (
                            old_state, new_state, self.env.user.name))

        # Log other important field changes — resolve display value per field type
        tracking_fields = ['source_warehouse_id', 'dest_warehouse_id', 'source_document']
        for field in tracking_fields:
            if field in vals:
                field_def = self._fields[field]
                for record in self:
                    old_value = getattr(record, field)
                    if hasattr(old_value, 'name'):
                        old_display = old_value.name
                    elif old_value:
                        old_display = str(old_value)
                    else:
                        old_display = _('Not set')

                    # Resolve new value display using the field's actual comodel, if any
                    if field_def.type == 'many2one' and vals[field]:
                        new_display = self.env[field_def.comodel_name].browse(vals[field]).name
                    else:
                        new_display = vals[field] or _('Not set')

                    record.message_post(body=_("%s changed from %s to %s by %s.") % (
                        field_def.string, old_display, new_display, self.env.user.name))

        return super(StockInternalTransfer, self).write(vals)

    def _backfill_requisition_id(self):
        """Backfill requisition_id for transfers that don't have it set"""
        transfers_without_requisition = self.search([('requisition_id', '=', False)])
        for transfer in transfers_without_requisition:
            requisition = self.env['material.purchase.requisition'].search([
                ('sgeede_transfer_id', '=', transfer.id)
            ], limit=1)
            if requisition:
                transfer.requisition_id = requisition.id
        return True

    def action_open_requisition(self):
        """Open the linked Purchase Requisition"""
        self.ensure_one()

        # Get the requisition_id directly from the database to avoid field conversion issues
        if not self.id:
            if not self.requisition_id:
                raise UserError(_("No Purchase Requisition linked to this transfer"))
            requisition_id = self.requisition_id.id
        else:
            # Get the raw requisition_id value from the database
            self.env.cr.execute(
                "SELECT requisition_id FROM stock_internal_transfer WHERE id = %s",
                (self.id,)
            )
            result = self.env.cr.fetchone()
            if not result or not result[0]:
                raise UserError(_("No Purchase Requisition linked to this transfer"))
            requisition_id = result[0]

        # Verify the requisition exists
        requisition = self.env['material.purchase.requisition'].browse(requisition_id)
        if not requisition.exists():
            raise UserError(_("The linked Purchase Requisition has been deleted"))

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'material.purchase.requisition',
            'res_id': requisition_id,
            'view_mode': 'form',
            'target': 'current',
            'context': self.env.context
        }


class StockInternalTransferLine(models.Model):
    _name = 'stock.internal.transfer.line'
    _inherit = ['mail.thread']
    _description = 'Stock Internal Transfer Line'

    name = fields.Char(string="Reference", tracking=True)
    product_id = fields.Many2one('product.product', string="Product", tracking=True)
    product_qty = fields.Float(string="Planned Quantity", tracking=True, default=1)
    total_planned_qty = fields.Float(
        string="Total Planned Qty",
        compute='_compute_total_planned_qty',
        store=False,
        help="Total planned quantity for this product across all lines in the transfer"
    )
    product_uom_id = fields.Many2one('uom.uom', string="Unit of Measure", tracking=True)
    qty_available = fields.Float(
        string="Available Quantity",
        compute='_compute_qty_available',
        store=True,
        help="Available quantity in source warehouse at time of transfer"
    )
    qty_sent = fields.Float(
        string="Sent Quantity",
        compute='_compute_qty_sent',
        store=True,
        help="Quantity actually sent to transit"
    )
    qty_received = fields.Float(
        string="Received Quantity",
        compute='_compute_qty_received',
        store=True,
        help="Quantity actually received by destination or returned to sender"
    )
    qty_in_transit = fields.Float(
        string="Quantity in Transit",
        compute='_compute_qty_in_transit',
        store=True,
        help="Quantity still in transit (sent but not received)"
    )
    state = fields.Selection(
        [('cancel', 'Cancel'), ('draft', 'Draft'), ('send', 'Sent'), ('done', 'Done')],
        string="Status",
        tracking=True,
        default="draft"
    )
    transfer_id = fields.Many2one('stock.internal.transfer', string="Transfer", tracking=True)
    lot_id = fields.Many2one('stock.lot', string="Lot")
    is_editable = fields.Boolean(compute='_compute_is_editable', string='Is Editable')

    # NEW FIELDS: Second UOM
    second_uom = fields.Integer(
        string='Second UOM',
        default=1,
        tracking=True,
        help="Second unit of measure for the product"
    )
    # FIXED: Changed from related field to computed field to avoid dependency on product.product.need_second_uom
    need_second_uom = fields.Boolean(
        string='Need Second UOM',
        compute='_compute_need_second_uom',
        store=True,
        help="Indicates if the product requires second UOM"
    )

    @api.depends('product_id')
    def _compute_need_second_uom(self):
        """Compute if product needs second UOM"""
        for line in self:
            if line.product_id:
                # Try to access need_second_uom on product, but handle gracefully if it doesn't exist
                try:
                    line.need_second_uom = line.product_id.need_second_uom
                except Exception:
                    # If field doesn't exist on product, default to False
                    line.need_second_uom = False
            else:
                line.need_second_uom = False

    @api.constrains('second_uom', 'need_second_uom')
    def check_second_uom(self):
        """Validate second_uom field"""
        for rec in self:
            if rec.need_second_uom:
                if rec.second_uom <= 0:
                    raise ValidationError(_("Second UOM Must Be Greater Than Zero."))

    @api.depends('transfer_id.state')
    def _compute_is_editable(self):
        for line in self:
            line.is_editable = line.transfer_id.state == 'draft'

    @api.onchange('product_id')
    def product_id_change(self):
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
            # Update available quantity when product changes
            if self.transfer_id and self.transfer_id.source_warehouse_id:
                self.qty_available = self._get_available_quantity()

    @api.depends('product_id', 'product_qty', 'transfer_id.line_ids.product_id', 'transfer_id.line_ids.product_qty',
                 'lot_id', 'transfer_id.line_ids.lot_id', 'qty_sent', 'transfer_id.line_ids.qty_sent',
                 'transfer_id.state')
    def _compute_total_planned_qty(self):
        """Set planned quantity for this line (not sum of all lines)
        After sending, equals qty_sent for this line; before sending, equals product_qty for this line.
        """
        for line in self:
            if line.transfer_id and line.transfer_id.state in ('send', 'partial_receive', 'receive', 'done'):
                line.total_planned_qty = line.qty_sent or 0.0
            else:
                line.total_planned_qty = line.product_qty or 0.0

    @api.depends('product_id', 'transfer_id.source_warehouse_id')
    def _compute_qty_available(self):
        for line in self:
            if line.product_id and line.transfer_id and line.transfer_id.source_warehouse_id:
                line.qty_available = line._get_available_quantity()
            else:
                line.qty_available = 0.0

    @api.depends('transfer_id.picking_ids', 'transfer_id.picking_ids.move_ids',
                 'transfer_id.picking_ids.move_ids.move_line_ids',
                 'transfer_id.picking_ids.move_ids.move_line_ids.quantity')
    def _compute_qty_sent(self):
        for line in self:
            sent_qty = 0.0
            rounding = line.product_uom_id.rounding if line.product_uom_id else 0.01
            if line.transfer_id and line.transfer_id.picking_ids:
                # Find sending pickings (source to transit)
                send_pickings = line.transfer_id.picking_ids.filtered(
                    lambda p: p.location_dest_id == line.transfer_id.company_id.transit_location_id
                              and p.state == 'done'
                )

                for picking in send_pickings:
                    for move in picking.move_ids:
                        if move.product_id.id == line.product_id.id and move.state == 'done':
                            # Check lot matching
                            if line.lot_id:
                                # Sum only move lines with matching lot
                                matching_lines = move.move_line_ids.filtered(
                                    lambda ml: ml.lot_id.id == line.lot_id.id
                                )
                                sent_qty += sum(matching_lines.mapped('quantity'))
                            else:
                                # Sum all move lines
                                sent_qty += sum(move.move_line_ids.mapped('quantity'))
            # Apply UoM rounding to eliminate floating-point imprecision
            line.qty_sent = float_round(sent_qty, precision_rounding=rounding)

    @api.depends('transfer_id.picking_ids', 'transfer_id.picking_ids.move_ids',
                 'transfer_id.picking_ids.move_ids.move_line_ids',
                 'transfer_id.picking_ids.move_ids.move_line_ids.quantity',
                 'product_id', 'lot_id', 'transfer_id.line_ids.product_id', 'transfer_id.line_ids.lot_id')
    def _compute_qty_received(self):
        """Compute received quantity - sums all received quantities for similar products across all lines"""
        # Process all lines together to ensure correct computation
        all_lines = self
        if not all_lines:
            return

        # Group by transfer to process each transfer's lines together
        transfers = all_lines.mapped('transfer_id')
        for transfer in transfers:
            transfer_lines = all_lines.filtered(lambda l: l.transfer_id.id == transfer.id)
            if not transfer_lines or not transfer.picking_ids:
                continue

            # Find receiving pickings (transit to destination)
            receive_pickings = transfer.picking_ids.filtered(
                lambda p: p.location_id == transfer.company_id.transit_location_id
                          and p.location_dest_id == transfer.dest_warehouse_id.lot_stock_id
                          and p.state == 'done'
            )

            # Find return pickings (transit to source)
            return_pickings = transfer.picking_ids.filtered(
                lambda p: p.location_id == transfer.company_id.transit_location_id
                          and p.location_dest_id == transfer.source_warehouse_id.lot_stock_id
                          and p.state == 'done'
            )

            # Collect all received quantities by product and lot
            received_by_product = {}
            for picking in receive_pickings:
                for move in picking.move_ids:
                    if move.state == 'done':
                        product_id = move.product_id.id
                        # Get lot from move lines
                        move_lots = move.move_line_ids.mapped('lot_id')
                        if move_lots:
                            for lot in move_lots:
                                key = (product_id, lot.id)
                                qty = sum(move.move_line_ids.filtered(
                                    lambda ml: ml.lot_id.id == lot.id
                                ).mapped('quantity'))
                                received_by_product[key] = received_by_product.get(key, 0) + qty
                        else:
                            # No lot - sum all move lines
                            key = (product_id, False)
                            qty = sum(move.move_line_ids.mapped('quantity'))
                            received_by_product[key] = received_by_product.get(key, 0) + qty

            # Add return quantities
            for picking in return_pickings:
                for move in picking.move_ids:
                    if move.state == 'done':
                        product_id = move.product_id.id
                        move_lots = move.move_line_ids.mapped('lot_id')
                        if move_lots:
                            for lot in move_lots:
                                key = (product_id, lot.id)
                                qty = sum(move.move_line_ids.filtered(
                                    lambda ml: ml.lot_id.id == lot.id
                                ).mapped('quantity'))
                                received_by_product[key] = received_by_product.get(key, 0) + qty
                        else:
                            key = (product_id, False)
                            qty = sum(move.move_line_ids.mapped('quantity'))
                            received_by_product[key] = received_by_product.get(key, 0) + qty

            # Assign received quantities to lines, applying UoM rounding
            for line in transfer_lines:
                if not line.product_id:
                    line.qty_received = 0.0
                    continue

                rounding = line.product_uom_id.rounding if line.product_uom_id else 0.01

                # Determine the key for this line
                if line.lot_id:
                    key = (line.product_id.id, line.lot_id.id)
                else:
                    # For lines without lot, sum all received quantities for this product (all lots and no lot)
                    total_received = 0.0
                    for (prod_id, lot_id), qty in received_by_product.items():
                        if prod_id == line.product_id.id:
                            total_received += qty
                    line.qty_received = float_round(total_received, precision_rounding=rounding)
                    continue

                # For lines with lot, use the specific lot quantity
                line.qty_received = float_round(
                    received_by_product.get(key, 0.0), precision_rounding=rounding
                )

    @api.depends('qty_sent', 'qty_received')
    def _compute_qty_in_transit(self):
        for line in self:
            line.qty_in_transit = max(0, line.qty_sent - line.qty_received)

    def _get_available_quantity(self):
        """Get available quantity in source warehouse"""
        self.ensure_one()
        if not self.product_id or not self.transfer_id.source_warehouse_id:
            return 0.0

        location = self.transfer_id.source_warehouse_id.lot_stock_id
        quants = self.env['stock.quant'].search([
            ('product_id', '=', self.product_id.id),
            ('location_id', '=', location.id),
            ('quantity', '>', 0)
        ])
        return sum(quants.mapped('quantity'))

    @api.model_create_multi
    def create(self, vals_list):
        res = super(StockInternalTransferLine, self).create(vals_list)
        for rec, vals in zip(res, vals_list):
            if not rec.product_id:
                rec.product_uom_id = False
                rec.need_second_uom = False
                rec.second_uom = 1
            else:
                rec.product_uom_id = rec.product_id.uom_id
                try:
                    rec.need_second_uom = rec.product_id.need_second_uom
                except Exception:
                    rec.need_second_uom = False
                # Only reset second_uom to 1 if it wasn't explicitly provided for this specific record
                if 'second_uom' not in vals:
                    rec.second_uom = 1
                # Update available quantity
                if rec.transfer_id and rec.transfer_id.source_warehouse_id:
                    rec.qty_available = rec._get_available_quantity()
        return res

    def unlink(self):
        """Log deletion of lines"""
        transfers = self.mapped('transfer_id')
        for line in self:
            line.transfer_id.message_post(body=_("Product %s removed from transfer by %s.") % (
                line.product_id.name, self.env.user.name
            ))
        return super(StockInternalTransferLine, self).unlink()


class StockTransitQuantity(models.Model):
    """Model to display transit quantities"""
    _name = 'stock.transit.quantity'
    _description = 'Transit Quantity'
    _order = 'transfer_id, product_id'
    _rec_name = 'product_id'

    transfer_id = fields.Many2one(
        'stock.internal.transfer',
        string='Transfer',
        required=True,
        ondelete='cascade'
    )
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        required=True
    )
    product_qty = fields.Float(
        string='Quantity in Transit',
        required=True
    )
    product_uom_id = fields.Many2one(
        'uom.uom',
        string='Unit of Measure',
        required=True
    )
    # NEW FIELDS: Second UOM for transit quantities
    second_uom = fields.Integer(
        string='Second UOM',
        default=1,
        help="Second unit of measure for the product in transit"
    )
    # FIXED: Changed from related field to computed field to avoid dependency on product.product.need_second_uom
    need_second_uom = fields.Boolean(
        string='Need Second UOM',
        compute='_compute_need_second_uom',
        store=True,
        readonly=True
    )

    @api.depends('product_id')
    def _compute_need_second_uom(self):
        """Compute if product needs second UOM"""
        for transit in self:
            if transit.product_id:
                # Try to access need_second_uom on product, but handle gracefully if it doesn't exist
                try:
                    transit.need_second_uom = transit.product_id.need_second_uom
                except Exception:
                    # If field doesn't exist on product, default to False
                    transit.need_second_uom = False
            else:
                transit.need_second_uom = False

    lot_id = fields.Many2one(
        'stock.lot',
        string='Lot/Serial'
    )
    send_picking_id = fields.Many2one(
        'stock.picking',
        string='Source Picking'
    )
    move_id = fields.Many2one(
        'stock.move',
        string='Stock Move'
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        related='transfer_id.company_id',
        store=True,
        readonly=True
    )
    # Fields for the report
    transfer_reference = fields.Char(
        string='Transfer Reference',
        related='transfer_id.name',
        store=True,
        readonly=True
    )
    transfer_date = fields.Datetime(
        string='Transfer Date',
        related='transfer_id.date',
        store=True,
        readonly=True
    )
    source_warehouse = fields.Many2one(
        'stock.warehouse',
        string='Source Warehouse',
        related='transfer_id.source_warehouse_id',
        store=True,
        readonly=True
    )
    dest_warehouse = fields.Many2one(
        'stock.warehouse',
        string='Destination Warehouse',
        related='transfer_id.dest_warehouse_id',
        store=True,
        readonly=True
    )
    partial_receive_reason = fields.Text(
        string='Partial Receive Reason',
        related='transfer_id.partial_receive_reason',
        store=True,
        readonly=True
    )
    transfer_state = fields.Selection(
        string='Transfer State',
        related='transfer_id.state',
        store=True,
        readonly=True
    )