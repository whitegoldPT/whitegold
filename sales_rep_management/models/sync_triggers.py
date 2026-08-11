# -*- coding: utf-8 -*-
import logging
from odoo import models, api

_logger = logging.getLogger(__name__)

def notify_sse_all_postcommit(env, reason):
    """Helper to trigger SSE notifications post-commit."""
    try:
        from odoo.addons.sales_rep_management.controllers.sse import notify_all
        env.cr.postcommit.add(lambda: notify_all(reason=reason))
    except Exception as e:
        _logger.error(f"SSE: Failed to register post-commit notification ({reason}): {e}")

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    @api.model_create_multi
    def create(self, vals_list):
        res = super().create(vals_list)
        notify_sse_all_postcommit(self.env, 'product_updated')
        return res

    def write(self, vals):
        res = super().write(vals)
        notify_sse_all_postcommit(self.env, 'product_updated')
        return res

    def unlink(self):
        res = super().unlink()
        notify_sse_all_postcommit(self.env, 'product_updated')
        return res

class ProductPricelist(models.Model):
    _inherit = 'product.pricelist'

    @api.model_create_multi
    def create(self, vals_list):
        res = super().create(vals_list)
        notify_sse_all_postcommit(self.env, 'pricelist_updated')
        return res

    def write(self, vals):
        res = super().write(vals)
        notify_sse_all_postcommit(self.env, 'pricelist_updated')
        return res

    def unlink(self):
        res = super().unlink()
        notify_sse_all_postcommit(self.env, 'pricelist_updated')
        return res

class ProductPricelistItem(models.Model):
    _inherit = 'product.pricelist.item'

    @api.model_create_multi
    def create(self, vals_list):
        res = super().create(vals_list)
        notify_sse_all_postcommit(self.env, 'pricelist_updated')
        return res

    def write(self, vals):
        res = super().write(vals)
        notify_sse_all_postcommit(self.env, 'pricelist_updated')
        return res

    def unlink(self):
        res = super().unlink()
        notify_sse_all_postcommit(self.env, 'pricelist_updated')
        return res

class LoyaltyProgram(models.Model):
    _inherit = 'loyalty.program'

    @api.model_create_multi
    def create(self, vals_list):
        res = super().create(vals_list)
        notify_sse_all_postcommit(self.env, 'promotion_updated')
        return res

    def write(self, vals):
        res = super().write(vals)
        notify_sse_all_postcommit(self.env, 'promotion_updated')
        return res

    def unlink(self):
        res = super().unlink()
        notify_sse_all_postcommit(self.env, 'promotion_updated')
        return res

class LoyaltyRule(models.Model):
    _inherit = 'loyalty.rule'

    @api.model_create_multi
    def create(self, vals_list):
        res = super().create(vals_list)
        notify_sse_all_postcommit(self.env, 'promotion_updated')
        return res

    def write(self, vals):
        res = super().write(vals)
        notify_sse_all_postcommit(self.env, 'promotion_updated')
        return res

    def unlink(self):
        res = super().unlink()
        notify_sse_all_postcommit(self.env, 'promotion_updated')
        return res

class LoyaltyReward(models.Model):
    _inherit = 'loyalty.reward'

    @api.model_create_multi
    def create(self, vals_list):
        res = super().create(vals_list)
        notify_sse_all_postcommit(self.env, 'promotion_updated')
        return res

    def write(self, vals):
        res = super().write(vals)
        notify_sse_all_postcommit(self.env, 'promotion_updated')
        return res

    def unlink(self):
        res = super().unlink()
        notify_sse_all_postcommit(self.env, 'promotion_updated')
        return res

class AccountPaymentTerm(models.Model):
    _inherit = 'account.payment.term'

    @api.model_create_multi
    def create(self, vals_list):
        res = super().create(vals_list)
        notify_sse_all_postcommit(self.env, 'payment_term_updated')
        return res

    def write(self, vals):
        res = super().write(vals)
        notify_sse_all_postcommit(self.env, 'payment_term_updated')
        return res

class ResPartner(models.Model):
    _inherit = 'res.partner'

    @api.model_create_multi
    def create(self, vals_list):
        res = super().create(vals_list)
        notify_sse_all_postcommit(self.env, 'partner_updated')
        return res

    def write(self, vals):
        res = super().write(vals)
        # Avoid flood for technical fields if necessary, but partner changes are usually important
        notify_sse_all_postcommit(self.env, 'partner_updated')
        return res

class SalesRepresentative(models.Model):
    _inherit = 'sales.representative'

    @api.model_create_multi
    def create(self, vals_list):
        res = super().create(vals_list)
        notify_sse_all_postcommit(self.env, 'sales_rep_updated')
        return res

    def write(self, vals):
        res = super().write(vals)
        notify_sse_all_postcommit(self.env, 'sales_rep_updated')
        return res

class SaleOrderSyncTrigger(models.Model):
    _inherit = 'sale.order'

    @api.model_create_multi
    def create(self, vals_list):
        res = super().create(vals_list)
        notify_sse_all_postcommit(self.env, 'sale_order_updated')
        return res

    def write(self, vals):
        res = super().write(vals)
        notify_sse_all_postcommit(self.env, 'sale_order_updated')
        return res

class SalesRepPaymentMethodInherit(models.Model):
    _inherit = 'sales.rep.payment.method'

    @api.model_create_multi
    def create(self, vals_list):
        res = super().create(vals_list)
        notify_sse_all_postcommit(self.env, 'payment_method_updated')
        return res

    def write(self, vals):
        res = super().write(vals)
        notify_sse_all_postcommit(self.env, 'payment_method_updated')
        return res

    def unlink(self):
        res = super().unlink()
        notify_sse_all_postcommit(self.env, 'payment_method_updated')
        return res

class SalesRepReturnReasonInherit(models.Model):
    _inherit = 'sales.rep.return.reason'

    @api.model_create_multi
    def create(self, vals_list):
        res = super().create(vals_list)
        notify_sse_all_postcommit(self.env, 'return_reason_updated')
        return res

    def write(self, vals):
        res = super().write(vals)
        notify_sse_all_postcommit(self.env, 'return_reason_updated')
        return res

# --- Balance Sync Triggers ---

class AccountMoveBalanceTrigger(models.Model):
    _inherit = 'account.move'

    @api.model_create_multi
    def create(self, vals_list):
        res = super().create(vals_list)
        # If any move is for a cash/bank journal, trigger balance sync
        for move in res:
            if move.journal_id.type in ['cash', 'bank']:
                notify_sse_all_postcommit(self.env, 'journal_updated')
                break
        return res

    def write(self, vals):
        res = super().write(vals)
        # State changes or amount changes affect balances
        if any(f in vals for f in ['state', 'amount_total', 'journal_id']):
            for move in self:
                if move.journal_id.type in ['cash', 'bank']:
                    notify_sse_all_postcommit(self.env, 'journal_updated')
                    break
        return res

    def unlink(self):
        # Cache journal types before deletion if possible, or just notify
        has_bank_cash = any(m.journal_id.type in ['cash', 'bank'] for m in self)
        res = super().unlink()
        if has_bank_cash:
            notify_sse_all_postcommit(self.env, 'journal_updated')
        return res

class AccountPaymentBalanceTrigger(models.Model):
    _inherit = 'account.payment'

    @api.model_create_multi
    def create(self, vals_list):
        res = super().create(vals_list)
        notify_sse_all_postcommit(self.env, 'journal_updated')
        return res

    def write(self, vals):
        res = super().write(vals)
        notify_sse_all_postcommit(self.env, 'journal_updated')
        return res

    def unlink(self):
        res = super().unlink()
        notify_sse_all_postcommit(self.env, 'journal_updated')

        return res
