from odoo import models, fields, api, _
import logging
from odoo.exceptions import ValidationError
from dateutil.relativedelta import relativedelta
from dateutil.rrule import rrulestr
from datetime import time, datetime
import pytz

_logger = logging.getLogger(__name__)

class SalesRepresentative(models.Model):
    _name = 'sales.representative'
    _description = 'Sales Representative'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name'



    name = fields.Char(
        string='Name',
        required=True,
        tracking=True
    )
    code = fields.Char(
        string='Code',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New'),
        index=True
    )
    user_id = fields.Many2one(
        'res.users',
        string='User',
        required=True,
        ondelete='cascade'
    )
    employee_id = fields.Many2one(
        'hr.employee',
        string='Sales Rep',
    )
    supervisor_id = fields.Many2one(
        'sales.representative',
        string='Supervisor',
        domain="[('is_supervisor', '=', True)]"
    )
    crm_team_id = fields.Many2one(
        'crm.team',
        string='Sales Team',
        tracking=True
    )
    is_supervisor = fields.Boolean(
        string='Is Supervisor',
        default=False
    )
    is_manager = fields.Boolean(
        string='Is Manager',
        default=False
    )
    phone = fields.Char(
        string='Phone',
        related='employee_id.work_phone',
        store=True
    )
    email = fields.Char(
        string='Email',
        related='employee_id.work_email',
        readonly=True,
        store=True
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company
    )
    active = fields.Boolean(
        string='Active',
        default=True
    )
    territory_ids = fields.Many2many(
        'res.partner.category',
        string='Territories',
        help='Assigned territories for this sales rep'
    )
    team_member_ids = fields.One2many(
        'sales.representative',
        'supervisor_id',
        string='Team Members'
    )

    # Statistics
    total_routes = fields.Integer(
        string='Total Routes',
        compute='_compute_statistics'
    )
    total_visits = fields.Integer(
        string='Total Visits',
        compute='_compute_statistics'
    )
    total_collections = fields.Float(
        string='Total Collections',
        compute='_compute_statistics'
    )

    mobile_access_token = fields.Char(
        string='Mobile Access Token',
        index=True,
        copy=False,
        help="Access token issued by the master server for mobile sync."
    )
    monthly_target = fields.Float(
        string='Monthly Target'
    )
    is_driver = fields.Boolean(
        related='employee_id.is_driver',
        string="Is Driver",
        store=True,
        readonly=True
    )

    license_number = fields.Char(
        related='employee_id.license_number',
        string="License Number",
        readonly=True
    )
    license_issue_date = fields.Date(
        related='employee_id.license_issue_date',
        string="Issue Date",
        readonly=True
    )
    license_expiry_date = fields.Date(
        related='employee_id.license_expiry_date',
        string="Expiry Date",
        readonly=True
    )
    license_attachment = fields.Binary(
        related='employee_id.license_attachment',
        string="License Scan",
        readonly=True
    )
    get_notify = fields.Boolean(
        related='employee_id.get_notify',
        string="Get Expiration Notifications",
        readonly=True
    )
    notify_before_days = fields.Integer(
        related='employee_id.notify_before_days',
        string="Notify Before (Days)",
        readonly=True
    )
    notification_type = fields.Selection(
        related='employee_id.notification_type',
        string="Notification Method",
        readonly=True
    )
    notification_recipient_ids = fields.Many2many(
        related='employee_id.notification_recipient_ids',
        string="Recipients",
        readonly=True
    )

    # --- POS Configuration Fields ---
    
    # Accounting
    invoice_journal_id = fields.Many2one(
        'account.journal',
        string='Invoice Journal',
        domain="[('type', '=', 'sale')]",
        check_company=True,
        help="Journal used for invoices. If empty, uses Sales Journal"
    )
    fiscal_position_id = fields.Many2one(
        'account.fiscal.position',
        string='Default Fiscal Position',
        check_company=True,
        help="Default fiscal position for tax mapping"
    )

    # Inventory
    picking_type_id = fields.Many2one(
        'stock.picking.type',
        string='Operation Type',
        domain="[('code', '=', 'outgoing')]",
        check_company=True,
        help="Stock operation type for deliveries"
    )
    # stock_location_id = fields.Many2one(
    #     'stock.location',
    #     string='Stock Location',
    #     domain="[('usage', '=', 'internal')]",
    #     check_company=True,
    #     help="Location from which products are sold"
    # )
    return_location_id = fields.Many2one(
        'stock.location',
        string='Return Stock Location',
        domain="[('usage', '=', 'internal')]",
        check_company=True,
        help="Location from which products are returned"
    )

    # Products
    available_pricelist_ids = fields.Many2many(
        'product.pricelist',
        string='Available Pricelists',
        help="Pricelists available for this rep"
    )
    default_pricelist_id = fields.Many2one(
        'product.pricelist',
        string='Default Pricelist',
        help="Default pricelist for new orders"
    )
    product_category_ids = fields.Many2many(
        'product.category',
        string='Product Categories',
        help="Limit products to these categories. Leave empty for all."
    )

    # Payment Methods
    payment_method_ids = fields.Many2many(
        'sales.rep.payment.method',
        string='Payment Methods',
        check_company=True,
        help="Available payment methods"
    )
    payment_term_id = fields.Many2one(
        'account.payment.term',
        string='Payment Policy',
        check_company=True,
        tracking=True,
        help="Default payment terms applied to orders created by this representative"
    )


    # Settings
    # auto_confirm_order = fields.Boolean(
    #     string='Auto Confirm Orders',
    #     default=True
    # )
    # auto_create_invoice = fields.Boolean(
    #     string='Auto Create Invoice',
    #     default=True
    # )
    # auto_register_payment = fields.Boolean(
    #     string='Auto Register Payment',
    #     default=True
    # )
    # allow_partial_payment = fields.Boolean(
    #     string='Allow Partial Payment',
    #     default=False
    # )
    auto_delivery = fields.Boolean(
        string='Auto Delivery',
        default=False,
        help='Automatically process delivery and create invoice when confirming sales orders'
    )
    auto_receive = fields.Boolean(
        string='Auto Receive',
        default=False,
        help='Automatically validate return deliveries for this sales representative.'
    )

    default_location_id = fields.Many2one(
        'stock.location',
        string='Default Stock Location',
        domain=[('usage', '=', 'internal')],
        required=True,
        help='Location used as source for every delivery created from a route of this rep.'
    )

    @api.depends('name', 'code')
    def _compute_display_name(self):
        for record in self:
            record.display_name = f"[{record.code}] {record.name}"

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('code', _('New')) == _('New'):
                vals['code'] = self.env['ir.sequence'].next_by_code('sales.representative') or _('New')
        return super().create(vals_list)

    def write(self, vals):
        res = super(SalesRepresentative, self).write(vals)
        # Fields that should trigger a sync on the mobile app
        sync_trigger_fields = [
            'name',
            'email',
            'phone',
            'monthly_target',
            'auto_delivery',
            'auto_receive',
            'payment_method_ids', 
            'available_pricelist_ids', 
            'default_pricelist_id',
            'product_category_ids',
            'invoice_journal_id',
            'picking_type_id',
            'default_location_id',
            'return_location_id',
            'active',
            'user_id'
        ]
        if any(field in vals for field in sync_trigger_fields):
            try:
                from odoo.addons.sales_rep_management.controllers.sse import notify_sales_rep
                for record in self:
                    _logger.info("SSE: Triggering sync for representative %s due to profile update (%s)", record.name, list(vals.keys()))
                    notify_sales_rep(record.id, reason='profile_updated')
            except ImportError:
                pass
        return res

    def _compute_statistics(self):
        for record in self:
            routes = self.env['sales.rep.route'].search([('sales_rep_id', '=', record.id)])
            visits = self.env['sales.rep.visit'].search([('route_id.sales_rep_id', '=', record.id)])
            collections = self.env['sales.rep.collection'].search([
                ('visit_id.route_id.sales_rep_id', '=', record.id),
                ('state', '=', 'confirmed')
            ])

            record.total_routes = len(routes)
            record.total_visits = len(visits)
            record.total_collections = sum(collections.mapped('amount'))

    @api.constrains('supervisor_id')
    def _check_supervisor_hierarchy(self):
        for record in self:
            if record.supervisor_id:
                if record.supervisor_id == record:
                    raise ValidationError(_("A sales representative cannot be their own supervisor."))

                # Check for circular references
                current = record.supervisor_id
                while current:
                    if current == record:
                        raise ValidationError(_("Circular reference detected in supervisor hierarchy."))
                    current = current.supervisor_id

    def action_view_routes(self):
        """View routes for this sales representative"""
        return {
            'type': 'ir.actions.act_window',
            'name': _('Routes - %s') % self.name,
            'res_model': 'sales.rep.route',
            'view_mode': 'list,form',
            'domain': [('sales_rep_id', '=', self.id)],
            'context': {'default_sales_rep_id': self.id}
        }

    def action_view_visits(self):
        """View visits for this sales representative"""
        return {
            'type': 'ir.actions.act_window',
            'name': _('Visits - %s') % self.name,
            'res_model': 'sales.rep.visit',
            'view_mode': 'list,form',
            'domain': [('route_id.sales_rep_id', '=', self.id)],
            'context': {}
        }

    def action_view_collections(self):
        """View collections for this sales representative"""
        return {
            'type': 'ir.actions.act_window',
            'name': _('Collections - %s') % self.name,
            'res_model': 'sales.rep.collection',
            'view_mode': 'list,form',
            'domain': [('sales_rep_id', '=', self.id)],
            'context': {}
        }

    def action_view_license_attachment(self):
        """This method calls the view method on the related employee."""
        self.ensure_one()
        if not self.employee_id:
            raise ValidationError(_("No employee is linked to this representative."))
        return self.employee_id.action_view_attachment()



class SalesRepRoute(models.Model):
    _name = 'sales.rep.route'
    _description = 'Sales Representative Route'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, name'

    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company
    )
    name = fields.Char(
        string='Route Name',
        required=True,
        tracking=True
    )
    code = fields.Char(
        string='Route Code',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New'),
        index=True
    )
    sales_rep_id = fields.Many2one(
        'sales.representative',
        string='Sales Representative',
        required=True,
        tracking=True
    )
    supervisor_id = fields.Many2one(
        'sales.representative',
        string='Supervisor',
        related='sales_rep_id.supervisor_id',
        store=True
    )
    date = fields.Date(
        string='Route Date',
        required=True,
        default=fields.Date.context_today,
        tracking=True
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('approved', 'Approved'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled')
    ], string='Status', default='draft', tracking=True)

    # Existing fields
    visit_ids = fields.One2many(
        'sales.rep.visit',
        'route_id',
        string='Visits'
    )

    # New fields for customer management
    route_customer_ids = fields.One2many(
        'sales.route.customer',
        'route_id',
        string='Route Customers'
    )

    # Related records fields
    sale_order_ids = fields.One2many(
        'sale.order',
        'route_id',
        string='Sales Orders'
    )

    pos_order_ids = fields.One2many(
        'pos.order',
        'route_id',
        string='POS Orders'
    )

    payment_ids = fields.One2many(
        'account.payment',
        'route_id',
        string='Payments'
    )

    # Route Planning
    start_time = fields.Datetime(
        string='Start Time',
        default=fields.Datetime.now
    )
    end_time = fields.Datetime(
        string='End Time'
    )
    planned_visits = fields.Integer(
        string='Planned Visits',
        compute='_compute_visit_stats'
    )
    completed_visits = fields.Integer(
        string='Completed Visits',
        compute='_compute_visit_stats'
    )
    completion_rate = fields.Float(
        string='Completion Rate (%)',
        compute='_compute_visit_stats'
    )

    # Targets
    sales_target = fields.Float(
        string='Sales Target'
    )
    collection_target = fields.Float(
        string='Collection Target'
    )

    # Actuals
    actual_sales = fields.Float(
        string='Actual Sales',
        compute='_compute_actuals'
    )
    actual_collections = fields.Float(
        string='Actual Collections',
        compute='_compute_actuals'
    )

    notes = fields.Text(
        string='Notes'
    )

    # for recurrence
    is_recurrent = fields.Boolean(
        string='Recurrent',
        default=False,
        help="Check this box to make the route recurrent."
    )
    repeat_interval = fields.Integer(
        string='Repeat Every',
        default=1,
        help="Number of time units to repeat the route."
    )
    repeat_unit = fields.Selection([
        ('day', 'Days'),
        ('week', 'Weeks'),
        ('month', 'Months'),
        ('year', 'Years'),
    ], string='Repeat Unit', default='day', help="Unit of time for recurrence.")
    end_condition = fields.Selection([
        ('forever', 'Forever'),
        ('until', 'Until'),
    ], string='End Condition', default='forever', help="Specify if recurrence ends.")
    show_recurrent_hours = fields.Boolean(
        string='Show Hours Grid',
        default=False
    )
    reccurent_hour = fields.Selection([
        (str(float(h)), f"{h if 1 <= h <= 12 else (h-12 if h > 12 else 12)} {'AM' if h < 12 else 'PM'}")
        for h in range(24)
    ], string='Recurrent Hour', default='8.0', help="Hour at which the route will recur.")
    until_date = fields.Date(
        string='Until Date',
        help="Date until which the route will recur."
    )

    def _create_recurrent_routes(self):
        today = fields.Date.today()
        # Find all routes that are recurrent and active
        recurrent_routes = self.search([
            ('is_recurrent', '=', True),
            '|',
            ('end_condition', '=', 'forever'),
            ('until_date', '>=', today)
        ])

        for route in recurrent_routes:
            try:
                last_date = route.date
                if route.repeat_unit == 'day':
                    delta = relativedelta(days=route.repeat_interval)
                elif route.repeat_unit == 'week':
                    delta = relativedelta(weeks=route.repeat_interval)
                elif route.repeat_unit == 'month':
                    delta = relativedelta(months=route.repeat_interval)
                elif route.repeat_unit == 'year':
                    delta = relativedelta(years=route.repeat_interval)
                else:
                    continue

                next_date = last_date
                # Find the next occurrence that is on or after today
                while next_date < today:
                    next_date += delta

                # If the next date is past the 'until_date', stop recurrence
                if route.end_condition == 'until' and next_date > route.until_date:
                    route.write({'is_recurrent': False})
                    continue

                # Check if a route for this rep on this date already exists
                existing = self.search([
                    ('id', '!=', route.id),
                    ('sales_rep_id', '=', route.sales_rep_id.id),
                    ('date', '=', next_date)
                ], limit=1)
                if existing:
                    continue

                route.route_customer_ids.write({
                    'state': 'planned',
                    'visit_start_time': False,
                    'visit_end_time': False,
                    'visit_notes': False,
                    'visit_result': False,
                    'visit_id': False,
                })

                # Calculate start_time from reccurent_hour (Selection value is a string float)
                tz_name = route.sales_rep_id.user_id.tz or self.env.user.tz or 'UTC'
                user_tz = pytz.timezone(tz_name)
                
                # Convert selection string to float
                float_hour = float(route.reccurent_hour or 0.0)
                hour = int(float_hour)
                minute = int(round((float_hour - hour) * 60))
                
                # Combine date and time in user's timezone, then convert to UTC
                local_dt = user_tz.localize(datetime.combine(next_date, time(hour, minute)))
                utc_dt = local_dt.astimezone(pytz.UTC).replace(tzinfo=None)

                # Update the main route record for the new day
                route.write({
                    'date': next_date,
                    'state': 'in_progress',
                    'start_time': utc_dt,
                    'end_time': False,
                })
            except Exception as e:
                _logger.error("Failed to create recurrent route for route %s: %s", route.name, str(e))
                continue
        return True

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('code', _('New')) == _('New'):
                vals['code'] = self.env['ir.sequence'].next_by_code('sales.rep.route') or _('New')
        res = super().create(vals_list)
        
        # SSE Notification: Notify new representative (Post-Commit)
        try:
            from odoo.addons.sales_rep_management.controllers.sse import notify_sales_rep
            for route in res:
                if route.sales_rep_id:
                    rep_id = route.sales_rep_id.id
                    rep_name = route.sales_rep_id.name
                    _logger.debug("SSE: Registering post-commit notify for NEW representative %s", rep_name)
                    self.env.cr.postcommit.add(lambda: notify_sales_rep(rep_id, reason='route_created'))
        except Exception as e:
            _logger.warning("SSE: Failed to register notification for route creation: %s", e)
            
        return res

    def write(self, vals):
        # Capture affected representatives BEFORE the update
        reps_to_notify = set()
        for route in self:
            if route.sales_rep_id:
                reps_to_notify.add(route.sales_rep_id.id)
        
        res = super().write(vals)
        
        # Capture affected representatives AFTER the update (to catch new assignments)
        for route in self:
            if route.sales_rep_id:
                reps_to_notify.add(route.sales_rep_id.id)
        
        # SSE Notification: Notify everyone who was or is assigned to these routes (Post-Commit)
        if reps_to_notify:
            try:
                from odoo.addons.sales_rep_management.controllers.sse import notify_sales_rep
                def notify_reps():
                    for rep_id in reps_to_notify:
                        _logger.info("SSE: Triggering sync for representative ID %s due to route update", rep_id)
                        notify_sales_rep(rep_id, reason='route_updated')
                
                self.env.cr.postcommit.add(notify_reps)
            except Exception as e:
                _logger.warning("SSE: Failed to register notification for route update: %s", e)
            
        return res

    def unlink(self):
        # Capture affected representatives BEFORE deletion
        reps_to_notify = set()
        for route in self:
            if route.sales_rep_id:
                reps_to_notify.add(route.sales_rep_id.id)
                
        # Notify POST-COMMIT
        if reps_to_notify:
            try:
                from odoo.addons.sales_rep_management.controllers.sse import notify_sales_rep
                def notify_reps_deletion():
                    for rep_id in reps_to_notify:
                        _logger.info("SSE: Triggering sync for representative ID %s after route deletion", rep_id)
                        notify_sales_rep(rep_id, reason='route_deleted')
                
                self.env.cr.postcommit.add(notify_reps_deletion)
            except Exception as e:
                _logger.warning("SSE: Failed to register notification for route deletion: %s", e)
            
        return super().unlink()

    @api.depends('visit_ids', 'date')
    def _compute_visit_stats(self):
        for route in self:
            # For recurrent routes, filter visits by the current route date
            route_date = route.date
            visits = route.visit_ids
            if route_date:
                # visit_time is a datetime, so we compare its date()
                visits = visits.filtered(lambda v: v.visit_time and v.visit_time.date() == route_date)
            
            total_count = len(visits)
            completed_count = len(visits.filtered(lambda v: v.state == 'completed'))
            
            route.planned_visits = total_count
            route.completed_visits = completed_count
            route.completion_rate = (completed_count / total_count) if total_count else 0

    @api.depends('sale_order_ids', 'payment_ids', 'date')
    def _compute_actuals(self):
        for route in self:
            # For recurrent routes, we only want to count orders/payments from the current route date
            route_date = route.date
            
            orders = route.sale_order_ids.filtered(lambda r: r.date_order and r.date_order.date() == route_date) if route_date else route.sale_order_ids
            payments = route.payment_ids.filtered(lambda r: r.date and r.date == route_date) if route_date else route.payment_ids
            
            route.actual_sales = sum(orders.mapped('amount_total'))
            route.actual_collections = sum(payments.mapped('amount'))

    def action_approve(self):
        self.state = 'approved'
        return True

    def action_start(self):
        self.state = 'in_progress'
        self.start_time = fields.Datetime.now()
        return True

    def action_complete(self):
        self.state = 'completed'
        self.end_time = fields.Datetime.now()
        return True

    def action_cancel(self):
        self.state = 'cancelled'
        return True

    def action_reset_to_draft(self):
        self.state = 'draft'
        return True

    def action_view_visits(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Visits - %s') % self.name,
            'res_model': 'sales.rep.visit',
            'view_mode': 'list,form',
            'domain': [('route_id', '=', self.id)],
            'context': {'default_route_id': self.id}
        }

    def action_view_collections(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Collections - %s') % self.name,
            'res_model': 'sales.rep.collection',
            'view_mode': 'list,form',
            'domain': [('visit_id.route_id', '=', self.id)],
            'context': {}
        }

    def action_add_customer(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Add Customer to Route'),
            'res_model': 'sales.route.customer',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_route_id': self.id,
                'default_sales_rep_id': self.sales_rep_id.id
            }
        }


class SalesRouteCustomer(models.Model):
    _name = 'sales.route.customer'
    _description = 'Route Customer'
    _order = 'sequence, id'

    route_id = fields.Many2one(
        'sales.rep.route',
        string='Route',
        required=True,
        ondelete='cascade'
    )
    sales_rep_id = fields.Many2one(
        'sales.representative',
        string='Sales Representative',
        related='route_id.sales_rep_id',
        store=True
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Customer',
        required=True,
        # domain=[('customer_rank', '>', 0)]
    )
    sequence = fields.Integer(
        string='Sequence',
        default=10
    )
    state = fields.Selection([
        ('planned', 'Planned'),
        ('in_progress', 'Visit In Progress'),
        ('visited', 'Visited'),
        ('cancelled', 'Cancelled')
    ], string='Status', default='planned')

    # Visit information
    visit_type_id = fields.Many2one(
        'sales.rep.visit.types',
        string='Visit Type'
    )
    visit_start_time = fields.Datetime(string='Visit Start Time')
    visit_end_time = fields.Datetime(string='Visit End Time')
    visit_duration = fields.Char(string='Visit Duration', compute='_compute_visit_duration')
    visit_notes = fields.Text(string='Visit Notes')
    visit_result = fields.Selection([
        ('successful', 'Successful'),
        ('customer_unavailable', 'Customer Unavailable'),
        ('refused', 'Refused'),
        ('closed', 'Location Closed'),
        ('rescheduled', 'Rescheduled')
    ], string='Visit Result')

    # Related records
    visit_id = fields.Many2one('sales.rep.visit', string='Related Visit')
    
    # Location tracking
    visit_location_lat = fields.Char(string='Visit Latitude')
    visit_location_long = fields.Char(string='Visit Longitude')

    sale_order_ids = fields.One2many('sale.order', 'route_customer_id', string='Sales Orders')
    pos_order_ids = fields.One2many('pos.order', 'route_customer_id', string='POS Orders')
    payment_ids = fields.One2many('account.payment', 'route_customer_id', string='Payments')

    # Add company_id to fix the domain issue
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        related='route_id.sales_rep_id.user_id.company_id',
        store=True
    )

    @api.depends('visit_start_time', 'visit_end_time')
    def _compute_visit_duration(self):
        for record in self:
            if record.visit_start_time and record.visit_end_time:
                start = record.visit_start_time
                end = record.visit_end_time
                diff = end - start
                seconds = int(diff.total_seconds())
                hours, remainder = divmod(seconds, 3600)
                minutes, seconds = divmod(remainder, 60)
                record.visit_duration = f"{hours:02}:{minutes:02}:{seconds:02}"
            else:
                record.visit_duration = "00:00:00"

    def action_start_visit(self):
        """Start visit - create visit record and update state without redirecting"""
        self.ensure_one()
        self.state = 'in_progress'
        self.visit_start_time = fields.Datetime.now()

        # Create a visit record if one doesn't exist
        if not self.visit_id:
            visit = self.env['sales.rep.visit'].create({
                'name': self.env['ir.sequence'].next_by_code('sales.rep.visit') or _('New'),
                'route_id': self.route_id.id,
                'partner_id': self.partner_id.id,
                'route_customer_id': self.id,  # LINK TO ROUTE CUSTOMER
                'planned_time': fields.Datetime.now(),
                'visit_type': 'sales',
                'state': 'in_progress'
            })
            self.visit_id = visit.id
        else:
            # Update existing visit - only update fields that exist
            self.visit_id.write({
                'state': 'in_progress',
                'planned_time': fields.Datetime.now()
            })

        # Return True to stay on the same page and refresh the view
        return True

    def action_end_visit(self):
        """End visit - open visit result wizard"""
        self.ensure_one()
        self.visit_end_time = fields.Datetime.now()

        # Open visit result wizard
        return {
            'type': 'ir.actions.act_window',
            'name': _('Complete Visit'),
            'res_model': 'visit.result.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_route_customer_id': self.id,
                'default_visit_id': self.visit_id.id
            }
        }

    def action_create_sale_order(self):
        """Create sales order and link to visit"""
        self.ensure_one()

        # Check if we have a visit record from starting the visit
        if not self.visit_id:
            raise ValidationError(_("Please start the visit first before creating a sales order."))

        # Create the sale order and link it to the visit and route customer
        sale_order = self.env['sale.order'].create({
            'partner_id': self.partner_id.id,
            'route_id': self.route_id.id,
            'route_customer_id': self.id,
            'visit_id': self.visit_id.id,
            'origin': f"Route: {self.route_id.name} - Visit: {self.visit_id.name}",
            'date_order': fields.Datetime.now(),
        })

        # Link the sale order and complete the visit automatically
        self.visit_id.write({
            'state': 'completed',
            'visit_result': 'successful',
            'visit_time': fields.Datetime.now(),
            'sale_order_id': sale_order.id,
            'sale_amount': sale_order.amount_total
        })

        # Update route customer state
        self.state = 'visited'
        self.visit_end_time = fields.Datetime.now()

        return {
            'type': 'ir.actions.act_window',
            'name': _('Sales Order'),
            'res_model': 'sale.order',
            'res_id': sale_order.id,
            'view_mode': 'form',
            'target': 'current',
        }

    @api.model_create_multi
    def create(self, vals_list):
        res = super().create(vals_list)
        # Notify representative of the route
        try:
            from odoo.addons.sales_rep_management.controllers.sse import notify_sales_rep
            for record in res:
                if record.route_id.sales_rep_id:
                    notify_sales_rep(record.route_id.sales_rep_id.id, reason='customer_added_to_route')
        except Exception:
            pass
        return res

    def write(self, vals):
        # Capture affected representatives
        reps_to_notify = set()
        for record in self:
            if record.route_id.sales_rep_id:
                reps_to_notify.add(record.route_id.sales_rep_id.id)
                
        res = super().write(vals)
        
        # Notify after update
        for record in self:
            if record.route_id.sales_rep_id:
                reps_to_notify.add(record.route_id.sales_rep_id.id)
                
        if reps_to_notify:
            try:
                from odoo.addons.sales_rep_management.controllers.sse import notify_sales_rep
                for rep_id in reps_to_notify:
                    notify_sales_rep(rep_id, reason='customer_route_updated')
            except Exception:
                pass
        return res

    def unlink(self):
        # Capture affected representatives BEFORE deletion
        reps_to_notify = set()
        for record in self:
            # Use sudo() to ensure we can read the sales_rep_id even during deletion
            if record.sudo().route_id.sales_rep_id:
                reps_to_notify.add(record.route_id.sales_rep_id.id)
                
        res = super().unlink()

        if reps_to_notify:
            try:
                from odoo.addons.sales_rep_management.controllers.sse import notify_sales_rep
                for rep_id in reps_to_notify:
                    notify_sales_rep(rep_id, reason='customer_removed_from_route')
            except Exception:
                pass
        return res

    def action_create_pos_order(self):
        """Open POS interface and handle order completion"""
        self.ensure_one()

        # Check if we have a visit record from starting the visit
        if not self.visit_id:
            raise ValidationError(_("Please start the visit first before creating a POS order."))

        # Find an open POS session for current user
        pos_session = self.env['pos.session'].search([
            ('state', '=', 'opened'),
            ('user_id', '=', self.env.user.id)
        ], limit=1)

        if not pos_session:
            # Create a new POS session if none exists
            config = self.env['pos.config'].search([], limit=1)
            if not config:
                raise ValidationError(_("No POS configuration found. Please set up POS first."))

            pos_session = self.env['pos.session'].create({
                'config_id': config.id,
                'user_id': self.env.user.id,
            })
            pos_session.action_pos_session_open()

        # Store the visit and route customer information in the session for later linking
        pos_session.write({
            'current_route_customer_id': self.id,
            'current_visit_id': self.visit_id.id,
            'current_route_id': self.route_id.id,
        })

        # Open POS interface with the customer pre-selected
        return {
            'type': 'ir.actions.act_url',
            'url': f'/pos/ui?session_id={pos_session.id}',
            'target': 'self',
        }

    def action_create_payment(self):
        """Create customer payment and link to visit"""
        self.ensure_one()

        # Check if we have a visit record from starting the visit
        if not self.visit_id:
            raise ValidationError(_("Please start the visit first before creating a payment."))

        # Create payment record and link it to visit and route customer
        payment = self.env['account.payment'].create({
            'payment_type': 'inbound',
            'partner_type': 'customer',
            'partner_id': self.partner_id.id,
            'amount': 1.0,  # Set default amount to 1.0 to avoid validation error
            'route_id': self.route_id.id,
            'route_customer_id': self.id,
            'visit_id': self.visit_id.id,
            'date': fields.Date.today(),
            'journal_id': self._get_default_journal().id,
        })

        # Create a collection record linked to the visit with the same amount
        collection = self.env['sales.rep.collection'].create({
            'name': self.env['ir.sequence'].next_by_code('sales.rep.collection') or _('New'),
            'visit_id': self.visit_id.id,
            'collection_date': fields.Datetime.now(),
            'amount': 1.0,  # Set default amount to 1.0
            'payment_method': 'cash',
            'state': 'draft'
        })

        # Complete the visit automatically when payment is saved
        self.visit_id.write({
            'state': 'completed',
            'visit_result': 'successful',
            'visit_time': fields.Datetime.now(),
        })

        # Update route customer state
        self.state = 'visited'
        self.visit_end_time = fields.Datetime.now()

        return {
            'type': 'ir.actions.act_window',
            'name': _('Customer Payment'),
            'res_model': 'account.payment',
            'res_id': payment.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _get_default_journal(self):
        """Get default journal for payments"""
        journal = self.env['account.journal'].search([
            ('type', 'in', ['bank', 'cash']),
            ('company_id', '=', self.env.company.id)
        ], limit=1)

        if not journal:
            # Fallback to any journal
            journal = self.env['account.journal'].search([
                ('company_id', '=', self.env.company.id)
            ], limit=1)

        return journal

    def action_view_related_orders(self):
        """View related orders for this route customer"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Related Orders'),
            'res_model': 'sale.order',
            'view_mode': 'list,form',
            'domain': [('route_customer_id', '=', self.id)],
            'context': {'create': False}
        }