from odoo import models, fields, api, _
from odoo.exceptions import UserError


class SalesRepPerformanceReport(models.TransientModel):
    _name = 'sales.rep.performance.report'
    _description = 'Sales Representative Performance Report'
    _auto = False
    _log_access = True

    sales_rep_id = fields.Many2one('sales.representative', string='Sales Representative')
    route_id = fields.Many2one('sales.rep.route', string='Route')
    visit_id = fields.Many2one('sales.rep.visit', string='Visit')

    # Count fields
    sale_order_count = fields.Integer(string='Sales Orders')
    pos_order_count = fields.Integer(string='POS Orders')
    payment_count = fields.Integer(string='Payments')

    # Amount fields
    sale_order_total = fields.Float(string='Sales Order Total')
    pos_order_total = fields.Float(string='POS Order Total')
    payment_total = fields.Float(string='Payment Total')
    total_amount = fields.Float(string='Grand Total')

    # Quantity fields
    sale_order_qty = fields.Float(string='Sales Order Qty')
    pos_order_qty = fields.Float(string='POS Order Qty')
    total_qty = fields.Float(string='Total Quantity')

    # Hierarchy fields
    level = fields.Integer(string='Level')
    parent_id = fields.Integer(string='Parent ID')

    # Display name field
    display_name = fields.Char(string='Name', compute='_compute_display_name')

    @api.depends('sales_rep_id', 'route_id', 'visit_id', 'level')
    def _compute_display_name(self):
        for record in self:
            if record.level == 1 and record.sales_rep_id:
                record.display_name = f"📊 {record.sales_rep_id.name}"
            elif record.level == 2 and record.route_id:
                record.display_name = f"🗺️ {record.route_id.name}"
            elif record.level == 3 and record.visit_id:
                record.display_name = f"👥 {record.visit_id.partner_id.name} - {record.visit_id.visit_type}"
            else:
                record.display_name = "Unknown"

    def init(self):
        """Initialize the report view"""
        self._cr.execute("""
            DROP VIEW IF EXISTS sales_rep_performance_report;
            CREATE OR REPLACE VIEW sales_rep_performance_report AS (
                -- Level 1: Sales Representatives
                SELECT 
                    sr.id AS id,
                    sr.id AS sales_rep_id,
                    NULL::integer AS route_id,
                    NULL::integer AS visit_id,
                    1 AS level,
                    0 AS parent_id,
                    COUNT(DISTINCT so.id) AS sale_order_count,
                    COUNT(DISTINCT po.id) AS pos_order_count,
                    COUNT(DISTINCT ap.id) AS payment_count,
                    COALESCE(SUM(so.amount_total), 0) AS sale_order_total,
                    COALESCE(SUM(po.amount_total), 0) AS pos_order_total,
                    COALESCE(SUM(ap.amount), 0) AS payment_total,
                    COALESCE(SUM(so.amount_total), 0) + COALESCE(SUM(po.amount_total), 0) + COALESCE(SUM(ap.amount), 0) AS total_amount,
                    COALESCE(SUM(sol.product_uom_qty), 0) AS sale_order_qty,
                    COALESCE(SUM(pol.qty), 0) AS pos_order_qty,
                    COALESCE(SUM(sol.product_uom_qty), 0) + COALESCE(SUM(pol.qty), 0) AS total_qty
                FROM sales_representative sr
                LEFT JOIN sales_rep_route srr ON srr.sales_rep_id = sr.id
                LEFT JOIN sale_order so ON so.route_id = srr.id
                LEFT JOIN sale_order_line sol ON sol.order_id = so.id
                LEFT JOIN pos_order po ON po.route_id = srr.id
                LEFT JOIN pos_order_line pol ON pol.order_id = po.id
                LEFT JOIN account_payment ap ON ap.route_id = srr.id
                WHERE sr.active = True
                GROUP BY sr.id

                UNION ALL

                -- Level 2: Routes
                SELECT 
                    (1000000 + srr.id) AS id,
                    srr.sales_rep_id AS sales_rep_id,
                    srr.id AS route_id,
                    NULL::integer AS visit_id,
                    2 AS level,
                    srr.sales_rep_id AS parent_id,
                    COUNT(DISTINCT so.id) AS sale_order_count,
                    COUNT(DISTINCT po.id) AS pos_order_count,
                    COUNT(DISTINCT ap.id) AS payment_count,
                    COALESCE(SUM(so.amount_total), 0) AS sale_order_total,
                    COALESCE(SUM(po.amount_total), 0) AS pos_order_total,
                    COALESCE(SUM(ap.amount), 0) AS payment_total,
                    COALESCE(SUM(so.amount_total), 0) + COALESCE(SUM(po.amount_total), 0) + COALESCE(SUM(ap.amount), 0) AS total_amount,
                    COALESCE(SUM(sol.product_uom_qty), 0) AS sale_order_qty,
                    COALESCE(SUM(pol.qty), 0) AS pos_order_qty,
                    COALESCE(SUM(sol.product_uom_qty), 0) + COALESCE(SUM(pol.qty), 0) AS total_qty
                FROM sales_rep_route srr
                LEFT JOIN sale_order so ON so.route_id = srr.id
                LEFT JOIN sale_order_line sol ON sol.order_id = so.id
                LEFT JOIN pos_order po ON po.route_id = srr.id
                LEFT JOIN pos_order_line pol ON pol.order_id = po.id
                LEFT JOIN account_payment ap ON ap.route_id = srr.id
                GROUP BY srr.id, srr.sales_rep_id

                UNION ALL

                -- Level 3: Visits
                SELECT 
                    (2000000 + srv.id) AS id,
                    srv.sales_rep_id AS sales_rep_id,
                    srv.route_id AS route_id,
                    srv.id AS visit_id,
                    3 AS level,
                    (1000000 + srv.route_id) AS parent_id,
                    COUNT(DISTINCT so.id) AS sale_order_count,
                    COUNT(DISTINCT po.id) AS pos_order_count,
                    COUNT(DISTINCT ap.id) AS payment_count,
                    COALESCE(SUM(so.amount_total), 0) AS sale_order_total,
                    COALESCE(SUM(po.amount_total), 0) AS pos_order_total,
                    COALESCE(SUM(ap.amount), 0) AS payment_total,
                    COALESCE(SUM(so.amount_total), 0) + COALESCE(SUM(po.amount_total), 0) + COALESCE(SUM(ap.amount), 0) AS total_amount,
                    COALESCE(SUM(sol.product_uom_qty), 0) AS sale_order_qty,
                    COALESCE(SUM(pol.qty), 0) AS pos_order_qty,
                    COALESCE(SUM(sol.product_uom_qty), 0) + COALESCE(SUM(pol.qty), 0) AS total_qty
                FROM sales_rep_visit srv
                LEFT JOIN sale_order so ON so.visit_id = srv.id
                LEFT JOIN sale_order_line sol ON sol.order_id = so.id
                LEFT JOIN pos_order po ON po.visit_id = srv.id
                LEFT JOIN pos_order_line pol ON pol.order_id = po.id
                LEFT JOIN account_payment ap ON ap.visit_id = srv.id
                GROUP BY srv.id, srv.sales_rep_id, srv.route_id
            )
        """)