from odoo import models, fields, api, _
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import logging

_logger = logging.getLogger(__name__)


class SalesRepDashboard(models.TransientModel):
    _name = 'sales.rep.dashboard'
    _description = 'Sales Representative Dashboard'

    # Date Filters
    date_from = fields.Date(
        string='From Date',
        default=lambda self: fields.Date.context_today(self).replace(day=1)
    )
    date_to = fields.Date(
        string='To Date',
        default=fields.Date.context_today
    )
    sales_rep_id = fields.Many2one(
        'sales.representative',
        string='Sales Representative'
    )
    
    # KPI Fields
    total_routes = fields.Integer(string='Total Routes')
    completed_routes = fields.Integer(string='Completed Routes')
    total_visits = fields.Integer(string='Total Visits')
    completed_visits = fields.Integer(string='Completed Visits')
    total_sales = fields.Float(string='Total Sales')
    total_collections = fields.Float(string='Total Payments')
    route_completion_rate = fields.Float(string='Route Completion Rate (%)')
    visit_completion_rate = fields.Float(string='Visit Completion Rate (%)')
    collection_efficiency = fields.Float(string='Payment Efficiency (%)')
    
    # Top Performers
    top_sales_rep_ids = fields.Many2many(
        'sales.representative',
        'dashboard_top_sales_rel',
        string='Top Sales Performers'
    )
    top_collection_rep_ids = fields.Many2many(
        'sales.representative',
        'dashboard_top_collection_rel',
        string='Top Collection Performers'
    )
    
    @api.model
    def get_dashboard_stats(self, date_from=None, date_to=None, sales_rep_id=None):
        """Get combined dashboard statistics for the OWL component"""
        # Convert strings to dates if necessary
        if isinstance(date_from, str):
            date_from = fields.Date.from_string(date_from)
        if isinstance(date_to, str):
            date_to = fields.Date.from_string(date_to)
            
        # Set defaults if not provided
        if not date_from:
            date_from = fields.Date.context_today(self).replace(day=1)
        if not date_to:
            date_to = fields.Date.context_today(self)
            
        domain = [('date', '>=', date_from), ('date', '<=', date_to)]
        if sales_rep_id:
            domain.append(('sales_rep_id', '=', sales_rep_id))
            
        # Get routes data
        routes = self.env['sales.rep.route'].search(domain)
        completed_routes = routes.filtered(lambda r: r.state == 'completed')
        
        _logger.info("Dashboard Stats: Found %s routes (%s completed) for domain %s", len(routes), len(completed_routes), domain)
        
        # Get financial data from routes
        orders = routes.mapped('sale_order_ids').filtered(lambda r: r.state not in ['draft', 'cancel'])
        payments_acc = routes.mapped('payment_ids').filtered(lambda r: r.state in ['posted', 'in_payment', 'reconciled'])
        
        total_sales = sum(orders.mapped('amount_total'))
        total_payments = sum(payments_acc.mapped('amount'))
        
        _logger.info("Dashboard Stats: Found %s routes, %s orders (Total: %s), %s payments (Total: %s)", 
                     len(routes), len(orders), total_sales, len(payments_acc), total_payments)
        
        # Get visits data
        visits = routes.mapped('visit_ids')
        completed_visits = visits.filtered(lambda v: v.state == 'completed')
        
        _logger.info("Dashboard Stats: Found %s visits (%s completed)", len(visits), len(completed_visits))
        
        # Calculate KPIs
        total_routes = len(routes)
        done_routes = len(completed_routes)
        total_visits = len(visits)
        done_visits = len(completed_visits)
        
        route_completion = (done_routes / total_routes * 100) if total_routes else 0
        visit_completion = (done_visits / total_visits * 100) if total_visits else 0
        efficiency = (total_payments / total_sales * 100) if total_sales else 0
        
        # Donut Chart Data: Route Status Distribution
        route_status_counts = {}
        for r in routes:
            st = r.state
            route_status_counts[st] = route_status_counts.get(st, 0) + 1
            
        # Stacked Bar Chart Data: Daily Visit Completion
        # Group visits by route date
        daily_visits = {}
        current_date = date_from
        while current_date <= date_to:
            daily_visits[current_date] = {'total': 0, 'completed': 0}
            current_date += timedelta(days=1)
            
        for visit in visits:
            v_date = visit.route_id.date
            if v_date in daily_visits:
                daily_visits[v_date]['total'] += 1
                if visit.state == 'completed':
                    daily_visits[v_date]['completed'] += 1
                    
        daily_data = []
        for d in sorted(daily_visits.keys()):
            stats = daily_visits[d]
            daily_data.append({
                'date': d.strftime('%m/%d'),
                'total': stats['total'],
                'completed': stats['completed'],
                'pending': stats['total'] - stats['completed']
            })
            
        return {
            'kpis': {
                'total_routes': total_routes,
                'completed_routes': done_routes,
                'total_visits': total_visits,
                'completed_visits': done_visits,
                'total_sales': total_sales,
                'total_payments': total_payments,
                'route_completion': round(route_completion, 1),
                'visit_completion': round(visit_completion, 1),
                'efficiency': round(efficiency, 1),
            },
            'route_status_data': [
                {'status': s, 'count': c} for s, c in route_status_counts.items()
            ],
            'daily_visit_data': daily_data,
        }

    def get_dashboard_data(self):
        """Get dashboard data for current filters (used by Form View)"""
        # Call the model method with self's values
        stats = self.get_dashboard_stats(self.date_from, self.date_to, self.sales_rep_id.id)
        kpis = stats['kpis']
        
        # Update self fields
        self.total_routes = kpis['total_routes']
        self.completed_routes = kpis['completed_routes']
        self.total_visits = kpis['total_visits']
        self.completed_visits = kpis['completed_visits']
        self.total_sales = kpis['total_sales']
        self.total_collections = kpis['total_payments']
        self.route_completion_rate = kpis['route_completion']
        self.visit_completion_rate = kpis['visit_completion']
        self.collection_efficiency = kpis['efficiency']
        
        return True
    def get_top_customers_data(self):
        """Get top customers by sales/collections"""
        domain = [
            ('route_id.date', '>=', self.date_from),
            ('route_id.date', '<=', self.date_to),
            ('state', '=', 'completed')
        ]
        
        if self.sales_rep_id:
            domain.append(('route_id.sales_rep_id', '=', self.sales_rep_id.id))
        
        visits = self.env['sales.rep.visit'].search(domain)
        
        # Group by customer and sum sales
        customer_sales = {}
        customer_collections = {}
        
        for visit in visits:
            customer = visit.partner_id
            
            # Sales
            if customer.id in customer_sales:
                customer_sales[customer.id]['amount'] += visit.sale_amount
            else:
                customer_sales[customer.id] = {
                    'customer': customer.name,
                    'amount': visit.sale_amount
                }
            
            # Collections
            collections_amount = sum(
                visit.collection_ids.filtered(
                    lambda c: c.state in ['confirmed', 'reconciled']
                ).mapped('amount')
            )
            
            if customer.id in customer_collections:
                customer_collections[customer.id]['amount'] += collections_amount
            else:
                customer_collections[customer.id] = {
                    'customer': customer.name,
                    'amount': collections_amount
                }
        
        # Sort and get top 10
        top_sales = sorted(
            customer_sales.values(),
            key=lambda x: x['amount'],
            reverse=True
        )[:10]
        
        top_collections = sorted(
            customer_collections.values(),
            key=lambda x: x['amount'],
            reverse=True
        )[:10]
        
        return {
            'top_sales': top_sales,
            'top_collections': top_collections
        }
    
    def get_rep_performance_data(self):
        """Get performance comparison between sales reps"""
        if self.sales_rep_id:
            # If specific rep selected, compare with team members
            if self.sales_rep_id.supervisor_id:
                reps = self.sales_rep_id.supervisor_id.team_member_ids
            else:
                reps = self.env['sales.representative'].search([])
        else:
            # Get all active reps
            reps = self.env['sales.representative'].search([('active', '=', True)])
        
        performance_data = []
        
        for rep in reps:
            # Get rep's data for the period
            routes = self.env['sales.rep.route'].search([
                ('sales_rep_id', '=', rep.id),
                ('date', '>=', self.date_from),
                ('date', '<=', self.date_to)
            ])
            
            visits = routes.mapped('visit_ids').filtered(lambda v: v.state == 'completed')
            collections = visits.mapped('collection_ids').filtered(
                lambda c: c.state in ['confirmed', 'reconciled']
            )
            
            performance_data.append({
                'rep_name': rep.name,
                'total_visits': len(routes.mapped('visit_ids')),
                'completed_visits': len(visits),
                'total_sales': sum(visits.mapped('sale_amount')),
                'total_collections': sum(collections.mapped('amount')),
                'completion_rate': (
                    len(visits) / len(routes.mapped('visit_ids'))
                    if routes.mapped('visit_ids') else 0
                )
            })
        
        # Sort by total sales
        performance_data.sort(key=lambda x: x['total_sales'], reverse=True)
        
        return performance_data[:10]  # Top 10 performers
    
    def action_open_routes(self):
        """Open routes view with current filters"""
        domain = [('date', '>=', self.date_from), ('date', '<=', self.date_to)]
        
        if self.sales_rep_id:
            domain.append(('sales_rep_id', '=', self.sales_rep_id.id))
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Routes'),
            'res_model': 'sales.rep.route',
            'view_mode': 'list,form',
            'domain': domain,
            'context': {'default_date': self.date_to}
        }
    
    def action_open_visits(self):
        """Open visits view with current filters"""
        domain = [
            ('route_id.date', '>=', self.date_from),
            ('route_id.date', '<=', self.date_to)
        ]
        
        if self.sales_rep_id:
            domain.append(('route_id.sales_rep_id', '=', self.sales_rep_id.id))
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Visits'),
            'res_model': 'sales.rep.visit',
            'view_mode': 'list,form',
            'domain': domain
        }
    
    def action_open_collections(self):
        """Open collections view with current filters"""
        domain = [
            ('collection_date', '>=', self.date_from),
            ('collection_date', '<=', self.date_to)
        ]
        
        if self.sales_rep_id:
            domain.append(('sales_rep_id', '=', self.sales_rep_id.id))
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Collections'),
            'res_model': 'sales.rep.collection',
            'view_mode': 'list,form',
            'domain': domain
        }