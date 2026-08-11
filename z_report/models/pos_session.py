# -*- coding: utf-8 -*-

from odoo import api, fields, models

class PosSession(models.Model):
    _inherit = 'pos.session'

    closing_user_id = fields.Many2one('res.users', string='Closed By', readonly=True)

    def action_pos_session_close(self, balancing_account=False, amount_to_balance=0, bank_payment_method_diffs=None):
        res = super(PosSession, self).action_pos_session_close(balancing_account, amount_to_balance, bank_payment_method_diffs)
        for session in self:
            session.closing_user_id = self.env.user
        return res
