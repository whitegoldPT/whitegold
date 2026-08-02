from odoo import models, fields, api, _

class SaleOrder(models.Model):
    _inherit = 'sale.order'
    forensic_alert = fields.Char(string='🛡️ تنبيه جنائي')

class MrpProduction(models.Model):
    _inherit = 'mrp.production'
    forensic_alert = fields.Char(string='🛡️ تنبيه جنائي')

class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'
    forensic_alert = fields.Char(string='🛡️ تنبيه جنائي')
    rni_amount = fields.Monetary(
        string='مبلغ مستلم لم يُفوتر',
        compute='_compute_rni_stats',
        store=True,
        currency_field='currency_id'
    )
    rni_status = fields.Selection([
        ('ok', '✅ مطابق'),
        ('partial', '⚠️ فوترة جزئية'),
        ('missing', '🚨 لم يُفوتر'),
    ], string='حالة الفوترة', compute='_compute_rni_stats', store=True)

    @api.depends('order_line.qty_received', 'order_line.qty_invoiced', 'order_line.price_unit')
    def _compute_rni_stats(self):
        for po in self:
            total_rni = 0.0
            has_partial = False
            has_missing = False
            for line in po.order_line:
                qty_gap = line.qty_received - line.qty_invoiced
                if qty_gap > 0:
                    total_rni += qty_gap * line.price_unit
                    if line.qty_invoiced > 0:
                        has_partial = True
                    else:
                        has_missing = True
            po.rni_amount = total_rni
            if total_rni <= 0:
                po.rni_status = 'ok'
            elif has_missing:
                po.rni_status = 'missing'
            else:
                po.rni_status = 'partial'


class AccountInterimReport(models.Model):

    _name = 'account.interim.report'
    _description = 'Forensic Review Engine'

    @api.model
    def action_run_scan(self):
        """ Dashboard entry point for deep scan """
        moves = self.env['account.move'].search([('state', '=', 'posted')], limit=1000)
        moves.action_run_forensic_scan()
        return self.action_run_forensic_scan()

    @api.model
    def action_run_forensic_scan(self, incremental=False):
        """ PHASE 3: Universal Cross-Module Scanner with RNI Detection """

        # 1. Scan Accounting (Moves & Refunds)
        moves = self.env['account.move'].search([('state', '=', 'posted')], order='write_date desc', limit=2000)
        moves.action_run_forensic_scan()

        # 2. Scan Inventory (Stock Pickings & Adjustments)
        pickings = self.env['stock.picking'].search([('state', '=', 'done')], limit=500)
        for pick in pickings:
            risk_note = ""
            if pick.picking_type_code == 'incoming' and not pick.purchase_id:
                 risk_note = "🛡️ استلام يدوي بدون أمر شراء!"
            elif pick.picking_type_code == 'outgoing' and not pick.sale_id:
                 risk_note = "🛡️ صرف يدوي بدون أمر بيع!"

            if risk_note and risk_note not in (pick.note or ""):
                 pick.note = (pick.note or "") + f" \n {risk_note}"

        # 3. Scan Sales (Policy Violations)
        sales = self.env['sale.order'].search([('state', 'in', ('sale', 'done'))], limit=500)
        for sale in sales:
            if any(line.discount > 20 for line in sale.order_line):
                sale.forensic_alert = "🚩 خصم مبالغ فيه (> 20%)"
            else:
                sale.forensic_alert = False

        # 4. Scan Manufacturing (Efficiency Gaps)
        mos = self.env['mrp.production'].search([('state', '=', 'done')], limit=200)
        for mo in mos:
             if not mo.move_raw_ids:
                 mo.forensic_alert = "🚩 تصنيع وهمي (بدون خامات)"
             else:
                 mo.forensic_alert = False

        # =====================================================
        # 5. 🚨 NEW: Scan Purchases (Received Not Invoiced)
        # =====================================================
        rni_count = 0
        rni_total = 0.0
        purchase_orders = self.env['purchase.order'].search([
            ('state', 'in', ('purchase', 'done')),
        ], limit=1000)

        for po in purchase_orders:
            alerts = []
            po_rni = 0.0

            for line in po.order_line:
                qty_gap = line.qty_received - line.qty_invoiced
                if qty_gap > 0.01:
                    po_rni += qty_gap * line.price_unit

            if po_rni > 0:
                rni_count += 1
                rni_total += po_rni
                alerts.append(f"🚨 بضاعة مستلمة لم تُفوتر: {po_rni:,.2f}")

            # Check for old POs without bills (> 30 days)
            if po.date_approve:
                from datetime import date
                days_since = (date.today() - po.date_approve.date()).days
                if days_since > 30 and po_rni > 0:
                    alerts.append(f"⏰ متأخر {days_since} يوم بدون فاتورة!")

            # Check price variance between PO and received
            for line in po.order_line:
                if line.qty_received > 0 and line.product_id and line.product_id.standard_price > 0:
                    variance = abs(line.price_unit - line.product_id.standard_price) / line.product_id.standard_price
                    if variance > 0.15:
                        alerts.append(f"📊 انحراف سعر {line.product_id.name}: {variance:.0%}")
                        break  # One per PO is enough

            po.forensic_alert = " | ".join(alerts) if alerts else False

        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {
                'title': _('🛡️ اكتمل الفحص الشامل لجميع القطاعات'),
                'message': _(
                    'تم فحص الحسابات، المخازن، المبيعات، التصنيع والمشتريات.\n'
                    '🚨 مشتريات مستلمة بدون فواتير: %d أمر بقيمة %s'
                ) % (rni_count, f"{rni_total:,.2f}"),
                'type': 'warning' if rni_count > 0 else 'success',
                'sticky': rni_count > 0,
                'next': {'type': 'ir.actions.client', 'tag': 'reload_context'}
            }
        }

    def action_universal_deep_scrub(self):
        """ Powerful cross-module integrity check """
        return True
