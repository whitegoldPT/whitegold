from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    route_id = fields.Many2one('sales.rep.route', string='Sales Route', ondelete='set null')
    route_customer_id = fields.Many2one('sales.route.customer', string='Route Customer', ondelete='set null')
    visit_id = fields.Many2one('sales.rep.visit', string='Related Visit', ondelete='set null')
    sales_rep_id = fields.Many2one('sales.representative', string='Sales Rep', tracking=True, readonly=True)
    created_sales_rep_id = fields.Many2one(
        'sales.representative', 
        string='Created By Sales Rep', 
        help="The sales representative who created this order."
    )
    user_id = fields.Many2one(
        'res.users', string='Salesperson', index=True, tracking=True,
        default=lambda self: self.env.user,
        domain="['|', ('share', '=', True), ('share', '=', False)]")

    is_route_order = fields.Boolean(string='Is Route Order', compute='_compute_is_route_order', store=True)
    is_cash = fields.Boolean(string='Is Cash Order')
    partner_is_cash = fields.Boolean(related='partner_id.is_cash', string='Partner Is Cash')
    mobile_local_id = fields.Char(string='Mobile Local ID', index=True)

    @api.onchange('partner_id')
    def _onchange_partner_id_is_cash(self):
        if self.partner_id:
            self.is_cash = getattr(self.partner_id, 'is_cash', False)


    @api.onchange('sales_rep_id')
    def _onchange_sales_rep_id(self):
        if self.sales_rep_id:
            if self.sales_rep_id.user_id:
                self.user_id = self.sales_rep_id.user_id
            if self.sales_rep_id.crm_team_id:
                self.team_id = self.sales_rep_id.crm_team_id
            # التعديلات الجديدة:
            if self.sales_rep_id.default_pricelist_id:
                self.pricelist_id = self.sales_rep_id.default_pricelist_id
           

    @api.onchange('user_id')
    def _onchange_user_id_set_team(self):
        if self.user_id:
            # Try to find a Sales Representative record
            rep = self.env['sales.representative'].search([('user_id', '=', self.user_id.id)], limit=1)
            if rep:
                if rep.crm_team_id:
                    self.team_id = rep.crm_team_id
                self.sales_rep_id = rep
            else:
                self.sales_rep_id = False

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # Determine user_id
            user_id = vals.get('user_id') or self.env.uid
            
            # Find the Sales Representative for the current user/assigned user
            rep = self.env['sales.representative'].search([('user_id', '=', user_id)], limit=1)
            
            # 1. Sync Sales Rep if not provided
            if not vals.get('sales_rep_id') and rep:
                vals['sales_rep_id'] = rep.id

            # 2. Set Created By Sales Rep (Only for mobile creation)
            if not vals.get('created_sales_rep_id') and vals.get('mobile_local_id'):
                current_user_rep = self.env['sales.representative'].search([('user_id', '=', self.env.uid)], limit=1)
                if current_user_rep:
                    vals['created_sales_rep_id'] = current_user_rep.id

        return super().create(vals_list)

    @api.depends('route_id')
    def _compute_is_route_order(self):
        for order in self:
            order.is_route_order = bool(order.route_id)

    def _action_confirm(self):
        res = super()._action_confirm()

        for order in self:
            location = False
            if order.route_id and order.route_id.sales_rep_id and order.route_id.sales_rep_id.default_location_id:
                location = order.route_id.sales_rep_id.default_location_id
            else:
                rep = order.env['sales.representative'].search([('user_id', '=', order.user_id.id)], limit=1)
                if rep and rep.default_location_id:
                    location = rep.default_location_id
                elif hasattr(order.user_id, 'location_id') and order.user_id.location_id:
                    location = order.user_id.location_id

            for picking in order.picking_ids:
                if order.sales_rep_id:
                    picking.sales_rep_id = order.sales_rep_id.id
                if location:
                    picking.location_id = location.id
                    for move in picking.move_ids_without_package:
                        move.location_id = location.id
                    for move_line in picking.move_line_ids:
                        move_line.location_id = location.id

        return res

    def _prepare_invoice(self):
        """Pass sales_rep_id to the invoice"""
        invoice_vals = super()._prepare_invoice()
        if self.sales_rep_id:
            invoice_vals['sales_rep_id'] = self.sales_rep_id.id
            invoice_vals['created_sales_rep_id'] = self.created_sales_rep_id.id if self.created_sales_rep_id else False
        return invoice_vals

    def _prepare_picking(self):
        """Pass sales_rep_id to the delivery picking"""
        result = super()._prepare_picking()
        if self.sales_rep_id:
            result['sales_rep_id'] = self.sales_rep_id.id
            result['created_sales_rep_id'] = self.created_sales_rep_id.id if self.created_sales_rep_id else False
        return result

    def _create_invoices(self, grouped=False, final=False, date=None):
        """Override to set invoice journal from sales rep configuration"""
        invoices = super()._create_invoices(grouped=grouped, final=final, date=date)
        
        for invoice in invoices:
            # Get the sales rep from the order
            order = invoice.line_ids.sale_line_ids.order_id[:1]
            if order:
                sales_rep = None
                # First check if the order has a route with a sales rep
                if order.route_id and order.route_id.sales_rep_id:
                    sales_rep = order.route_id.sales_rep_id
                else:
                    # Otherwise, find the sales rep by user_id
                    sales_rep = self.env['sales.representative'].search([
                        ('user_id', '=', order.user_id.id)
                    ], limit=1)
                
                if order.sales_rep_id:
                    sales_rep = order.sales_rep_id
                
                # If sales rep has an invoice journal configured, use it
                if sales_rep and sales_rep.invoice_journal_id:
                    invoice.write({'journal_id': sales_rep.invoice_journal_id.id})
        
        return invoices

class PosOrder(models.Model):
    _inherit = 'pos.order'

    route_id = fields.Many2one(
        'sales.rep.route',
        string='Sales Route',
        ondelete='set null'
    )

    route_customer_id = fields.Many2one(
        'sales.route.customer',
        string='Route Customer',
        ondelete='set null'
    )

    visit_id = fields.Many2one(
        'sales.rep.visit',
        string='Related Visit',
        ondelete='set null'
    )

    # Add a computed field to easily filter route-related orders
    is_route_order = fields.Boolean(
        string='Is Route Order',
        compute='_compute_is_route_order',
        store=True
    )

    @api.depends('route_id')
    def _compute_is_route_order(self):
        for order in self:
            order.is_route_order = bool(order.route_id)

    @api.model_create_multi
    def create(self, vals_list):
        """Override create to handle visit completion when POS order is created"""
        orders = super().create(vals_list)

        for order, vals in zip(orders, vals_list):
            # Link to route customer and visit if session has the information
            session = self.env['pos.session'].browse(vals.get('session_id'))
            if session and session.current_route_customer_id:
                route_customer = session.current_route_customer_id
                order.write({
                    'route_id': route_customer.route_id.id,
                    'route_customer_id': route_customer.id,
                    'visit_id': route_customer.visit_id.id
                })

                # Complete the visit
                if route_customer.visit_id and route_customer.visit_id.state == 'in_progress':
                    route_customer.visit_id.write({
                        'state': 'completed',
                        'visit_result': 'successful',
                        'visit_time': fields.Datetime.now(),
                        'sale_amount': order.amount_total
                    })

                    # Update route customer state
                    route_customer.write({
                        'state': 'visited',
                        'visit_end_time': fields.Datetime.now()
                    })

                    # Clear session data
                    session.write({
                        'current_route_customer_id': False,
                        'current_visit_id': False,
                        'current_route_id': False,
                    })

        return orders


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    def write(self, vals):
        res = super().write(vals)
        try:
            from odoo.addons.sales_rep_management.controllers.sse import notify_all
            skip_id = self.env.context.get('skip_notify_sales_rep_id')
            notify_all(reason='journal_updated', skip_sales_rep_id=skip_id)
        except ImportError:
            pass
        return res

class AccountPayment(models.Model):
    _inherit = 'account.payment'

    route_id = fields.Many2one(
        'sales.rep.route',
        string='Sales Route',
        ondelete='set null'
    )

    route_customer_id = fields.Many2one(
        'sales.route.customer',
        string='Route Customer',
        ondelete='set null'
    )

    visit_id = fields.Many2one(
        'sales.rep.visit',
        string='Related Visit',
        ondelete='set null'
    )

    mobile_local_id = fields.Char(string='Mobile Local ID', index=True)
    receipt_image = fields.Binary(string='Receipt Image')
    receipt_filename = fields.Char(string='Receipt Filename')

    # Add a computed field to easily filter route-related payments
    is_route_payment = fields.Boolean(
        string='Is Route Payment',
        compute='_compute_is_route_payment',
        store=True
    )

    @api.depends('route_id')
    def _compute_is_route_payment(self):
        for payment in self:
            payment.is_route_payment = bool(payment.route_id)

    def write(self, vals):
        res = super().write(vals)
        if 'state' in vals or 'amount' in vals:
            try:
                from odoo.addons.sales_rep_management.controllers.sse import notify_all
                skip_id = self.env.context.get('skip_notify_sales_rep_id')
                notify_all(reason='payment_updated', skip_sales_rep_id=skip_id)
            except ImportError:
                pass
        return res

    @api.model_create_multi
    def create(self, vals_list):
        """Override create to handle visit completion and linking when payment is created"""
        payments = super().create(vals_list)

        for payment in payments:
            # If this payment is linked to a route customer, link to visit and route if missing
            if payment.route_customer_id and payment.route_customer_id.visit_id:
                visit = payment.route_customer_id.visit_id
                
                update_vals = {}
                if not payment.visit_id:
                    update_vals['visit_id'] = visit.id
                if not payment.route_id and visit.route_id:
                    update_vals['route_id'] = visit.route_id.id
                
                if update_vals:
                    payment.write(update_vals)

                # Complete the visit if in progress
                if visit.state == 'in_progress':
                    visit.write({
                        'state': 'completed',
                        'visit_result': 'successful',
                        'visit_time': fields.Datetime.now()
                    })
                    # Update route customer state
                    payment.route_customer_id.write({
                        'state': 'visited',
                        'visit_end_time': fields.Datetime.now()
                    })
        
        try:
            from odoo.addons.sales_rep_management.controllers.sse import notify_all
            skip_id = self.env.context.get('skip_notify_sales_rep_id')
            notify_all(reason='payment_created', skip_sales_rep_id=skip_id)
        except ImportError:
            pass

        return payments


class AccountMove(models.Model):
    _inherit = 'account.move'

    mobile_local_id = fields.Char(string='Mobile Local ID', index=True)
    sales_rep_id = fields.Many2one(
        'sales.representative', 
        string='Sales Rep', 
        compute='_compute_sales_rep_id',
        store=True,
        tracking=True,
        readonly=True
    )
    created_sales_rep_id = fields.Many2one(
        'sales.representative', 
        string='Created By Sales Rep'
    )

    @api.depends('invoice_line_ids.sale_line_ids.order_id.sales_rep_id')
    def _compute_sales_rep_id(self):
        for move in self:
            if not move.sales_rep_id:
                # Find the sale order from the invoice lines
                order = move.line_ids.sale_line_ids.order_id[:1]
                if order and order.sales_rep_id:
                    move.sales_rep_id = order.sales_rep_id.id
                    if not move.created_sales_rep_id:
                        move.created_sales_rep_id = order.created_sales_rep_id.id

    def write(self, vals):
        res = super().write(vals)
        if any(f in vals for f in ['state', 'amount_total', 'date', 'journal_id']):
            try:
                from odoo.addons.sales_rep_management.controllers.sse import notify_all
                skip_id = self.env.context.get('skip_notify_sales_rep_id')
                notify_all(reason='move_updated', skip_sales_rep_id=skip_id)
            except ImportError:
                pass
        return res

    def action_post(self):
        res = super().action_post()
        try:
            from odoo.addons.sales_rep_management.controllers.sse import notify_all
            skip_id = self.env.context.get('skip_notify_sales_rep_id')
            notify_all(reason='move_posted', skip_sales_rep_id=skip_id)
        except ImportError:
            pass
        return res

class AccountBankStatementLine(models.Model):
    _inherit = 'account.bank.statement.line'

    def write(self, vals):
        res = super().write(vals)
        try:
            from odoo.addons.sales_rep_management.controllers.sse import notify_all
            skip_id = self.env.context.get('skip_notify_sales_rep_id')
            notify_all(reason='statement_line_updated', skip_sales_rep_id=skip_id)
        except ImportError:
            pass
        return res

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        try:
            from odoo.addons.sales_rep_management.controllers.sse import notify_all
            skip_id = self.env.context.get('skip_notify_sales_rep_id')
            notify_all(reason='statement_line_created', skip_sales_rep_id=skip_id)
        except ImportError:
            pass
        return records



class StockPicking(models.Model):
    _inherit = 'stock.picking'

    return_reason_id = fields.Many2one('sales.rep.return.reason', string='Return Reason')
    sales_rep_id = fields.Many2one(
        'sales.representative', 
        string='Sales Rep', 
        compute='_compute_sales_rep_id',
        store=True,
        tracking=True,
        readonly=True
    )
    created_sales_rep_id = fields.Many2one(
        'sales.representative', 
        string='Created By Sales Rep'
    )

    @api.depends('sale_id.sales_rep_id', 'move_ids.sale_line_id.order_id.sales_rep_id')
    def _compute_sales_rep_id(self):
        for picking in self:
            if not picking.sales_rep_id:
                order = picking.sale_id
                if not order and picking.move_ids:
                    order = picking.move_ids.sale_line_id.order_id[:1]
                
                if order and order.sales_rep_id:
                    picking.sales_rep_id = order.sales_rep_id.id
                    if not picking.created_sales_rep_id:
                        picking.created_sales_rep_id = order.created_sales_rep_id.id

    def _prepare_backorder_picking_vals(self):
        """Ensure sales_rep_id is copied to backorders"""
        res = super()._prepare_backorder_picking_vals()
        if self.sales_rep_id:
            res['sales_rep_id'] = self.sales_rep_id.id
            res['created_sales_rep_id'] = self.created_sales_rep_id.id if self.created_sales_rep_id else False
        return res

    def _log_activity_get_documents(self, *args, **kwargs):
        """
        Suppresses the automatic creation of activities for exceptions.
        """
        return {}

class StockMove(models.Model):
    _inherit = 'stock.move'

    def _get_new_picking_values(self):
        """Pass sales_rep_id from sale order to the new picking"""
        vals = super()._get_new_picking_values()
        # Find the sale order from the move
        order = self.sale_line_id.order_id or self.picking_id.sale_id
        if order and order.sales_rep_id:
            vals['sales_rep_id'] = order.sales_rep_id.id
            vals['created_sales_rep_id'] = order.created_sales_rep_id.id if order.created_sales_rep_id else False
        return vals

class PosSession(models.Model):
    _inherit = 'pos.session'

    current_route_customer_id = fields.Many2one(
        'sales.route.customer',
        string='Current Route Customer'
    )

    current_visit_id = fields.Many2one(
        'sales.rep.visit',
        string='Current Visit'
    )

    current_route_id = fields.Many2one(
        'sales.rep.route',
        string='Current Route'
    )
class ProductPricelist(models.Model):
    _inherit = 'product.pricelist'
    
    is_sales_cash = fields.Boolean(
        string='Sales Cash',
        default=False,
        help="Check if this pricelist is used for Sales Cash operations"
    )

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    # إضافة حقل مرتبط بقائمة الأسعار ليظهر في أمر البيع نفسه
    pricelist_is_sales_cash = fields.Boolean(
        related='pricelist_id.is_sales_cash',
        string='Sales Cash Pricelist',
        readonly=True
    )
