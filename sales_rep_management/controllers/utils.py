from odoo.http import request
import json
import logging

_logger = logging.getLogger(__name__)

class SalesRepUtils:
    def _get_sales_rep(self, user_id=None):
        # Try to get data from params or JSON body
        params = request.params or {}
        data = {}
        try:
            if request.httprequest.data:
                data = json.loads(request.httprequest.data)
        except Exception:
            pass
            
        sales_rep_id = params.get('sales_rep_id') or data.get('sales_rep_id')
        user_email = params.get('user_email') or data.get('user_email')
        
        # 1. Try by sales_rep_id
        if sales_rep_id:
            try:
                sales_rep = request.env['sales.representative'].sudo().browse(int(sales_rep_id))
                if sales_rep.exists():
                    return sales_rep
            except (ValueError, TypeError):
                pass
                 
        # 2. Try by email
        if user_email:
            sales_rep = request.env['sales.representative'].sudo().search([
                '|', ('email', '=', user_email), ('user_id.login', '=', user_email)
            ], limit=1)
            if sales_rep:
                return sales_rep

        if user_id:
            return request.env['sales.representative'].sudo().search([('user_id', '=', user_id)], limit=1)
            
        return request.env['sales.representative'].sudo()

    def _authenticate_token(self, token):
        """
        Authenticate the Bearer token against local sales.representative records.
        The token is provisioned during the tenant login step.
        """
        if not token:
            return None
            
        # 1. Find the Sales Rep by the provisioned mobile access token
        sales_rep = request.env['sales.representative'].sudo().search([
            ('mobile_access_token', '=', token),
            ('active', '=', True)
        ], limit=1)
        
        if not sales_rep:
            _logger.warning(f"Auth: Token {token[:10]}... not found in local sales representatives.")
            return None
            
        return sales_rep

    def _authenticate_request(self):
        """
        Helper to authenticate the current request via Bearer token.
        Returns (sales_rep, user) or (None, None).
        """
        auth_header = request.httprequest.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return None, None
        
        token = auth_header.split(' ')[1]
        sales_rep = self._authenticate_token(token)
        
        if not sales_rep or not sales_rep.user_id:
            return None, None
            
        return sales_rep, sales_rep.user_id
