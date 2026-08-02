# -*- coding: utf-8 -*-
from odoo import api, fields, models, _, exceptions
from odoo.tools import str2bool   # <-- minimal add

class SaleOrder(models.Model):
    _inherit = "sale.order"

    def action_confirm(self):
        """
        Block confirmation if any storable product has insufficient qty in the SO's warehouse.
        For multi-warehouse setups, we respect the picking type's warehouse on the order.
        """
        for order in self:
            warehouse = order.warehouse_id
            if not warehouse:
                continue

            stock_location = warehouse.lot_stock_id
            if not stock_location:
                continue

            icp = self.env["ir.config_parameter"].sudo()
            use_virtual = str2bool(icp.get_param("no_negative_stock.use_virtual", "0"))

            required = {}
            for line in order.order_line:
                product = line.product_id
                if not product or product.type != 'product':
                    continue
                qty = line.product_uom._compute_quantity(line.product_uom_qty, product.uom_id, rounding_method='HALF-UP')
                if qty <= 0:
                    continue
                required[product] = required.get(product, 0) + qty

            if not required:
                continue

            insufficient = []
            for product, need in required.items():
                prod_ctx = product.with_company(order.company_id).with_context(location=stock_location.id)

                if use_virtual and hasattr(prod_ctx, 'virtual_available'):
                    available = prod_ctx.virtual_available
                elif hasattr(prod_ctx, 'free_qty'):
                    available = prod_ctx.free_qty
                else:
                    available = prod_ctx.qty_available

                if available < need - 1e-6:
                    insufficient.append((product.display_name, need, available))

            if insufficient:
                details = "\n".join([f"- {name}: need {need:.2f}, available {avail:.2f}" for name, need, avail in insufficient])
                raise exceptions.UserError(_(
                    "Cannot confirm the quotation because some products are out of stock in warehouse '%s'.\n\n%s"
                ) % (warehouse.display_name, details))
        return super().action_confirm()
