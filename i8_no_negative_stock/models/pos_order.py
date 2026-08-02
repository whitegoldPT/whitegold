# -*- coding: utf-8 -*-
import logging
from collections import defaultdict
from odoo import api, models, _, exceptions

_logger = logging.getLogger(__name__)

def _iter_lines(order_data):

    candidates = []
    if isinstance(order_data, dict):
        if order_data.get('lines'):
            candidates.append(order_data['lines'])
        if isinstance(order_data.get('order'), dict) and order_data['order'].get('lines'):
            candidates.append(order_data['order']['lines'])

    for lines in candidates:
        for line in lines:
            if isinstance(line, (list, tuple)) and len(line) > 2 and isinstance(line[2], dict):
                vals = line[2]
            elif isinstance(line, dict):
                vals = line
            else:
                continue
            pid = vals.get('product_id') or vals.get('product')
            qty = vals.get('qty', vals.get('quantity', 0.0))
            if not pid or not qty or qty <= 0:
                continue
            yield int(pid), float(qty)

class PosOrder(models.Model):
    _inherit = "pos.order"

    def _check_pos_stock(self, order_data):
        session_id = order_data.get('pos_session_id') or order_data.get('session_id')
        session = self.env['pos.session'].browse(session_id)
        if not session.exists():
            _logger.info("i8_no_negative_stock: no session → skip")
            return

        config = session.config_id.sudo()
        if not config.block_out_of_stock:
            _logger.info("i8_no_negative_stock: toggle OFF → skip")
            return

        loc_id = (
            config.picking_type_id.warehouse_id.lot_stock_id.id
            if (config.picking_type_id and config.picking_type_id.warehouse_id and config.picking_type_id.warehouse_id.lot_stock_id)
            else (config.stock_location_id.id if config.stock_location_id else False)
        )
        if not loc_id:
            _logger.info("i8_no_negative_stock: no location resolved → skip")
            return

        # 1) Sum required qty per product
        needs = defaultdict(float)
        found_any = False
        for pid, qty in _iter_lines(order_data):
            found_any = True
            product = self.env['product.product'].browse(pid).exists()
            if not product:
                continue
            # Respect the toggle: if True, skip consumables; if False, check them too.
            if config.block_ignore_consumables and product.type != 'product':
                _logger.info("i8_no_negative_stock: skipping non-storable %s (type=%s) qty=%s", product.display_name, product.type, qty)
                continue
            needs[pid] += qty

        if not found_any:
            _logger.info("i8_no_negative_stock: no lines in payload → skip")
            return
        if not needs:
            _logger.info("i8_no_negative_stock: lines present but nothing to check (probably all non-storable and ignored)")
            return

        # 2) Compare against location availability and collect all shortages
        shortages = []
        for pid, need in needs.items():
            prod = self.env['product.product'] \
                .with_company(config.company_id) \
                .with_context(location=loc_id) \
                .browse(pid)
            available = (
                prod.virtual_available if config.block_use_forecast and hasattr(prod, 'virtual_available')
                else getattr(prod, 'free_qty', prod.qty_available)
            )
            _logger.info("i8_no_negative_stock: %s need=%.3f avail=%.3f @loc=%s", prod.display_name, need, available, loc_id)
            if available < need - 1e-6:
                shortages.append((prod.display_name, need, available))

        # 3) Raise one error listing every insufficient item
        if shortages:
            loc_name = self.env['stock.location'].browse(loc_id).display_name
            lines = "\n".join(f"- {name}: need {need:.2f}, available {avail:.2f}" for name, need, avail in shortages)
            raise exceptions.UserError(
                _("POS: Not enough stock in '%(loc)s' for:\n\n%(lines)s") % {"loc": loc_name, "lines": lines}
            )

        _logger.info("i8_no_negative_stock: all checks passed")

    @api.model
    def _process_order(self, order, *args, **kwargs):
        payload = order.get('data', order) if isinstance(order, dict) else order
        self._check_pos_stock(payload)
        return super()._process_order(order, *args, **kwargs)

    @api.model
    def create_from_ui(self, orders, **kwargs):
        for o in (orders or []):
            payload = o.get('data', o)
            self._check_pos_stock(payload)
        return super().create_from_ui(orders, **kwargs)

    def _create_picking(self, *args, **kwargs):
        for order in self:
            config = order.session_id.config_id.sudo()
            if not config.block_out_of_stock:
                continue
            loc_id = (
                config.picking_type_id.warehouse_id.lot_stock_id.id
                if (config.picking_type_id and config.picking_type_id.warehouse_id and config.picking_type_id.warehouse_id.lot_stock_id)
                else (config.stock_location_id.id if config.stock_location_id else False)
            )
            if not loc_id:
                continue

            needs = defaultdict(float)
            for line in order.lines:
                product = line.product_id
                if not product:
                    continue
                if config.block_ignore_consumables and product.type != 'product':
                    continue
                qty = float(line.qty or 0.0)
                if qty > 0:
                    needs[product.id] += qty

            shortages = []
            for pid, need in needs.items():
                prod = self.env['product.product'] \
                    .with_company(config.company_id) \
                    .with_context(location=loc_id) \
                    .browse(pid)
                available = (
                    prod.virtual_available if config.block_use_forecast and hasattr(prod, 'virtual_available')
                    else getattr(prod, 'free_qty', prod.qty_available)
                )
                if available < need - 1e-6:
                    shortages.append((prod.display_name, need, available))

            if shortages:
                loc_name = self.env['stock.location'].browse(loc_id).display_name
                lines = "\n".join(f"- {name}: need {need:.2f}, available {avail:.2f}" for name, need, avail in shortages)
                raise exceptions.UserError(
                    _("POS: Not enough stock in '%(loc)s' for:\n\n%(lines)s") % {"loc": loc_name, "lines": lines}
                )
        return super()._create_picking(*args, **kwargs)
