# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request
import json
import logging
from .utils import SalesRepUtils

_logger = logging.getLogger(__name__)

class AuthController(http.Controller, SalesRepUtils):

    @http.route('/api/mobile/login', type='http', auth='none', methods=['POST'], cors='*', csrf=False)
    def login(self, **post):
        try:
            data = json.loads(request.httprequest.data)
            db = data.get('db')
            login = data.get('login')
            password = data.get('password')
            email = data.get('email')

            # Ensure we have a database name from the payload or the current request
            db = db or request.db
            if db:
                request.session.db = db
            auth_info = request.session.authenticate(db, {'type': 'password', 'login': login, 'password': password})
            _logger.info(f"Auth: Login attempt for user '{login}' in database '{db}' with auth_info '{auth_info}'")
            uid = auth_info.get('uid')
            if uid:
                # Find the sales representative for this user
                sales_rep = False
                if email:
                    sales_rep = request.env['sales.representative'].sudo().search([('email', '=', email)], limit=1)
                
                if not sales_rep:
                    sales_rep = request.env['sales.representative'].sudo().search([('user_id', '=', uid)], limit=1)
                
                # Use provided token or current token or generate new one
                access_token = data.get('access_token')
                if not access_token and sales_rep:
                    access_token = sales_rep.mobile_access_token
                
                if not access_token and sales_rep:
                    import uuid
                    access_token = str(uuid.uuid4())
                    _logger.info(f"Auth: Generated new mobile_access_token for {sales_rep.name}")
                
                if sales_rep and access_token:
                    # Notify existing sessions to force logout before updating token
                    from .sse import notify_sales_rep
                    notify_sales_rep(sales_rep.id, reason='new_device_login', event_type='force_logout')
                    
                    sales_rep.write({'mobile_access_token': access_token})
                
                return request.make_response(json.dumps({
                    'success': True, 
                    'uid': uid, 
                    'session_id': request.session.sid,
                    'access_token': access_token
                }), headers={'Content-Type': 'application/json'})
            else:
                return request.make_response(json.dumps({'success': False, 'message': 'Invalid credentials'}), headers={'Content-Type': 'application/json'})
        except Exception as e:
            _logger.error(f"Error in login: {str(e)}")
            return request.make_response(json.dumps({'success': False, 'error': str(e)}), headers={'Content-Type': 'application/json'})

    @http.route('/api/mobile/logout', type='http', auth='none', methods=['GET'], cors='*', csrf=False)
    def logout(self, **kwargs):
        try:
            request.session.logout()
            return request.make_response(json.dumps({'success': True}), headers={'Content-Type': 'application/json'})
        except Exception as e:
            _logger.error(f"Error in logout: {str(e)}")
            return request.make_response(json.dumps({'success': False, 'error': str(e)}), headers={'Content-Type': 'application/json'})

    @http.route('/api/mobile/check_connection', type='http', auth='public', methods=['GET'], cors='*', csrf=False)
    def check_connection(self, **kwargs):
        try:
            sales_rep, user = self._authenticate_request()
            if not sales_rep:
                return request.make_response(json.dumps({'success': False, 'message': 'Unauthorized'}), headers={'Content-Type': 'application/json'}, status=401)
            return request.make_response(json.dumps({'success': True, 'message': 'Connection successful'}), headers={'Content-Type': 'application/json'})
        except Exception as e:
            return request.make_response(json.dumps({'success': False, 'error': str(e)}), headers={'Content-Type': 'application/json'})
