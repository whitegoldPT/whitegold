# -*- coding: utf-8 -*-
from odoo import models, fields, api
from markupsafe import escape as html_escape

class ForensicDashboard(models.TransientModel):
    _name = 'forensic.dashboard'
    _description = 'Professional Forensic Dashboard'

    name = fields.Char(default="Forensic Integrity Monitor")
    
    # Financial KPI Cards
    count_purchase = fields.Integer(string='Received Not Invoiced', compute='_compute_kpis')
    count_sale = fields.Integer(string='Price Variances', compute='_compute_kpis')
    count_inventory = fields.Integer(string='Stock Issues', compute='_compute_kpis')
    count_mfg = fields.Integer(string='Production Gaps', compute='_compute_kpis')
    count_general = fields.Integer(string='GL Anomalies', compute='_compute_kpis')
    count_gaps = fields.Integer(string='Sequence Gaps', compute='_compute_kpis')
    
    # RNI (Received Not Invoiced) Metrics
    rni_count = fields.Integer(string='أوامر شراء معلقة', compute='_compute_kpis')
    rni_total_amount = fields.Monetary(string='إجمالي مبالغ RNI', currency_field='company_currency', compute='_compute_kpis')
    
    # Risk Metrics
    total_risk_exposure = fields.Float(string='Risk Exposure Score', compute='_compute_kpis')
    amount_at_risk = fields.Monetary(string='Amount at Risk', currency_field='company_currency', compute='_compute_kpis')
    count_high_risk = fields.Integer(string='Critical Issues', compute='_compute_kpis')
    count_late_night = fields.Integer(string='Midnight Activity', compute='_compute_kpis')
    
    company_currency = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id)
    top_offenders_html = fields.Html(string='Top Risk Sources', compute='_compute_kpis')
    trust_index = fields.Float(string='Trust Index', compute='_compute_kpis')


    def _compute_kpis(self):
        Line = self.env['account.move.line']
        Move = self.env['account.move']
        
        # SQL Optimized Aggregation
        res_counts = Line._read_group([('audit_status', '=', 'pending')], ['forensic_category'], ['__count'])
        counts = {item[0]: item[1] for item in res_counts}

        self.env.cr.execute("SELECT SUM(risk_score), SUM(amount_total) FROM account_move WHERE risk_score > 0")
        sum_risk, sum_amount = self.env.cr.fetchone()
        
        # User analysis
        self.env.cr.execute("""
            SELECT rp.name, COUNT(am.id) FROM account_move am
            JOIN res_users ru ON ru.id = am.create_uid
            JOIN res_partner rp ON rp.id = ru.partner_id
            WHERE am.risk_score > 0 GROUP BY rp.name ORDER BY 2 DESC LIMIT 5
        """)
        top_users = self.env.cr.fetchall()

        for rec in self:
            # Purchases: Vendor Bills & Refunds with forensic risk
            rec.count_purchase = Move.search_count([('move_type', 'in', ('in_invoice', 'in_refund')), ('risk_score', '>', 0)])
            rec.count_sale = self.env['sale.order'].search_count([('forensic_alert', '!=', False)])
            rec.count_inventory = self.env['stock.picking'].search_count([('note', 'ilike', '🛡️')])
            rec.count_mfg = self.env['mrp.production'].search_count([('forensic_alert', '!=', False)])

            # RNI: Received Not Invoiced
            rni_pos = self.env['purchase.order'].search([('state', 'in', ('purchase', 'done')), ('rni_amount', '>', 0)])
            rec.rni_count = len(rni_pos)
            rec.rni_total_amount = sum(rni_pos.mapped('rni_amount'))

            
            rec.total_risk_exposure = sum_risk or 0.0
            rec.amount_at_risk = sum_amount or 0.0
            
            # General: Other moves with risks
            rec.count_general = Move.search_count([('move_type', '=', 'entry'), ('risk_score', '>', 0)])
            
            # Sequence Gaps (Professional numerical continuity check)
            self.env.cr.execute("""
                SELECT COUNT(*) FROM (
                    SELECT name, 
                           CAST(substring(name from '[0-9]+$') AS INTEGER) as seq_num,
                           lead(CAST(substring(name from '[0-9]+$') AS INTEGER)) OVER (PARTITION BY journal_id ORDER BY id) as next_seq
                    FROM account_move 
                    WHERE name IS NOT NULL AND name != '/' AND state = 'posted'
                ) s WHERE next_seq - seq_num > 1
            """)
            rec.count_gaps = self.env.cr.fetchone()[0] or 0
            
            rec.count_high_risk = Move.search_count([('risk_level', 'in', ('high', 'critical'))])

            rec.count_late_night = Move.search_count([('late_night_activity', '=', True)])
            
            total_moves = Move.search_count([('state', '=', 'posted')])
            moves_at_risk = Move.search_count([('risk_score', '>', 0)])
            if total_moves > 0:
                rec.trust_index = 100 * (1 - (moves_at_risk / total_moves))
            else:
                rec.trust_index = 100.0

            html = "<table class='table table-sm'><thead><tr><th>الموظف المسؤول</th><th>عدد المخالفات</th></tr></thead><tbody>"

            for user, count in top_users:
                html += f"<tr><td>{html_escape(str(user or ''))}</td><td>{count}</td></tr>"
            html += "</tbody></table>"
            rec.top_offenders_html = html



    def action_run_deep_scan(self):
        self.env['account.interim.report'].action_run_scan()
        return True

    def action_open_purchase_vouchers(self):
        view_id = self.env.ref('account_interim_report.view_move_tree_forensic_exclusive').id
        return {
            'name': 'فواتير ومردودات المشتريات المشبوهة', 'type': 'ir.actions.act_window',
            'res_model': 'account.move', 'view_mode': 'list,form',
            'views': [(view_id, 'list'), (False, 'form')],
            'domain': [('move_type', 'in', ('in_invoice', 'in_refund')), ('risk_score', '>', 0)],
            'context': {'default_move_type': 'in_invoice'}
        }

    def action_open_rni_center(self):
        """ Open Purchase Orders with Received Not Invoiced issues """
        view_id = self.env.ref('account_interim_report.view_purchase_order_tree_forensic_rni').id
        search_id = self.env.ref('account_interim_report.view_purchase_order_search_forensic_rni').id
        return {
            'name': '🚨 مشتريات مستلمة بدون فواتير',
            'type': 'ir.actions.act_window',
            'res_model': 'purchase.order',
            'view_mode': 'list,form',
            'views': [(view_id, 'list'), (False, 'form')],
            'search_view_id': search_id,
            'domain': [('state', 'in', ('purchase', 'done')), ('rni_amount', '>', 0)],
            'context': {'search_default_all_rni': 1}
        }

    def action_open_sale_vouchers(self):
        view_id = self.env.ref('account_interim_report.view_move_tree_forensic_exclusive').id
        return {
            'name': 'فواتير ومردودات المبيعات المشبوهة', 'type': 'ir.actions.act_window',
            'res_model': 'account.move', 'view_mode': 'list,form',
            'views': [(view_id, 'list'), (False, 'form')],
            'domain': [('move_type', 'in', ('out_invoice', 'out_refund')), ('risk_score', '>', 0)],
        }

    def action_open_stock_transfers(self):
        view_id = self.env.ref('account_interim_report.view_picking_tree_forensic_exclusive').id
        return {
            'name': 'أذون المخازن المشبوهة', 'type': 'ir.actions.act_window',
            'res_model': 'stock.picking', 'view_mode': 'list,form',
            'views': [(view_id, 'list'), (False, 'form')],
            'domain': [('note', 'ilike', '%🛡️%')],
        }


    def action_open_sale_orders(self):
        view_id = self.env.ref('account_interim_report.view_sale_order_tree_forensic_exclusive').id
        return {
            'name': 'أوامر البيع المشبوهة', 'type': 'ir.actions.act_window',
            'res_model': 'sale.order', 'view_mode': 'list,form',
            'views': [(view_id, 'list'), (False, 'form')],
            'domain': [('forensic_alert', '!=', False)],
        }

    def action_open_mrp_orders(self):
        view_id = self.env.ref('account_interim_report.view_production_tree_forensic_exclusive').id
        return {
            'name': 'أوامر التصنيع المشبوهة', 'type': 'ir.actions.act_window',
            'res_model': 'mrp.production', 'view_mode': 'list,form',
            'views': [(view_id, 'list'), (False, 'form')],
            'domain': [('forensic_alert', '!=', False)],
        }


