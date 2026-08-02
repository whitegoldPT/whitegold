# -*- coding: utf-8 -*-
import logging

from odoo import api, models, _
from odoo.exceptions import AccessError
from odoo.http import request

_logger = logging.getLogger(__name__)


class ResUsers(models.Model):
    _inherit = 'res.users'

    @api.model
    def pos_check_can_create_customer(self):
        """RPC method called from POS JS to check if the current user is
        allowed to create new customers in POS. Returns True or False."""
        return self.env.user.has_group(
            'pos_customer_create_access.group_pos_create_customer'
        )


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _is_pos_create_call(self):
        """Detect whether the current call originates from POS UI.

        Layered detection:
          1. Explicit POS context flags (most reliable when present).
          2. HTTP referrer pointing at /pos/ui or /pos/web (strong indicator).
          3. Active POS session for the current user combined with no other
             clear non-POS indicator (last-resort heuristic).
        """
        ctx = self.env.context or {}

        # 1) Explicit context flags
        if ctx.get('from_pos_ui'):
            return True
        if ctx.get('pos_session_id') or ctx.get('pos_config_id'):
            return True

        # 2) Inspect the current HTTP request — POS UI runs on /pos/ui
        try:
            if request and request.httprequest:
                referrer = request.httprequest.referrer or ''
                path = request.httprequest.path or ''
                if '/pos/ui' in referrer or '/pos/ui' in path:
                    return True
                if '/pos/web' in referrer or '/pos/web' in path:
                    return True
        except Exception:
            # request may not be available outside HTTP context (cron, tests)
            pass

        return False

    def _check_pos_create_permission(self):
        """Raise AccessError if user is creating partner in POS context
        but doesn't have the POS Create Customer group."""
        if not self._is_pos_create_call():
            return
        if self.env.user.has_group(
            'pos_customer_create_access.group_pos_create_customer'
        ):
            return
        _logger.info(
            "pos_customer_create_access: blocked partner.create() for user "
            "%s (id=%s) from POS context",
            self.env.user.login, self.env.user.id,
        )
        raise AccessError(_(
            "You do not have permission to create new customers from "
            "Point of Sale. Please contact your administrator."
        ))

    # ------------------------------------------------------------------
    # Overrides
    # ------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        self._check_pos_create_permission()
        return super().create(vals_list)
