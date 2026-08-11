# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
import json

class ForensicAuditLog(models.Model):
    _name = 'forensic.audit.log'
    _description = 'Forensic Event Record'
    _order = 'create_date desc'

    move_id = fields.Many2one('account.move', string='Journal Entry', ondelete='cascade', index=True)
    user_id = fields.Many2one('res.users', string='Employee', compute='_compute_user', store=True, default=lambda self: self.env.user)
    action = fields.Selection([
        ('create', '🆕 Setup'),
        ('write', '🛠️ Edit'),
        ('post', '🔒 Locking'),
        ('reverse', '⏪ Reverse'),
        ('fix', '🔧 Correction')
    ], string='Audit Event')

    snapshot_before = fields.Text(string='Before Action')
    snapshot_after = fields.Text(string='After Action')
    delta = fields.Text(string='Difference (Delta)')
    
    risk_score_impact = fields.Float(string='Risk Delta', help='Change in risk score after this move')

    def _compute_user(self):
        for log in self:
            if log.create_uid: log.user_id = log.create_uid
            else: log.user_id = self.env.user

    @api.model
    def create_snapshot(self, record, action='write', before_vals=None, after_vals=None):
        """
        Tool used to capture the state of a move for forensic tracking.
        """
        delta = {}
        if before_vals and after_vals:
            for key, val in after_vals.items():
                if key in before_vals and before_vals[key] != val:
                    delta[key] = {'old': before_vals[key], 'new': val}
        
        self.create({
            'move_id': record.id,
            'action': action,
            'snapshot_before': json.dumps(before_vals or {}),
            'snapshot_after': json.dumps(after_vals or {}),
            'delta': json.dumps(delta) if delta else False,
        })
