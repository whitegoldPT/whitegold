# -*- coding: utf-8 -*-
from odoo import models, fields, api

class AccountAccount(models.Model):
    _inherit = 'account.account'

    gl_balance = fields.Monetary(string='Mismatched Balance', compute='_compute_audit_stats')
    forensic_issues_count = fields.Integer(string='Pending Risks', compute='_compute_audit_stats')

    def _compute_audit_stats(self):
        if not self.ids:
            return
        # Single query for all accounts using read_group
        balance_data = self.env['account.move.line']._read_group(
            [('account_id', 'in', self.ids), ('reconciled', '=', False), ('parent_state', '=', 'posted')],
            ['account_id'],
            ['balance:sum', '__count']
        )
        balance_map = {item[0].id: {'balance': item[1], 'count': item[2]} for item in balance_data}
        
        issue_data = self.env['account.move.line']._read_group(
            [('account_id', 'in', self.ids), ('diagnostic_reason', '!=', False), ('parent_state', '=', 'posted')],
            ['account_id'],
            ['__count']
        )
        issue_map = {item[0].id: item[1] for item in issue_data}
        
        for acc in self:
            data = balance_map.get(acc.id, {'balance': 0.0, 'count': 0})
            acc.gl_balance = data['balance']
            acc.forensic_issues_count = issue_map.get(acc.id, 0)


    def action_open_audit_center(self):
        self.ensure_one()
        return {
            'name': f'تدقيق: {self.name}',
            'type': 'ir.actions.act_window',
            'res_model': 'account.move.line', 
            'view_mode': 'list,kanban,form', 
            'domain': [('account_id', '=', self.id), ('diagnostic_reason', '!=', False)],
        }
    def action_view_forensic_issues(self):
        self.ensure_one()
        return {
            'name': '🔎 المخاطر المكتشفة',
            'type': 'ir.actions.act_window',
            'res_model': 'account.move.line',
            'view_mode': 'list,form',
            'domain': [('account_id', '=', self.id), ('diagnostic_reason', '!=', False)],
            'context': {'search_default_audit_issues': 1}
        }

    def action_forensic_cleanup(self):
        """ PHASE 1 FIX: Optimized O(N) Reconciliation Logic """
        for acc in self:
            if not acc.reconcile: continue
            lines = self.env['account.move.line'].search([('account_id', '=', acc.id), ('reconciled', '=', False), ('parent_state', '=', 'posted')])
            match_map = {}
            for line in lines:
                key = (line.partner_id.id, abs(line.balance))
                if key not in match_map: match_map[key] = {'pos': [], 'neg': []}
                if line.balance > 0: match_map[key]['pos'].append(line)
                else: match_map[key]['neg'].append(line)
            for key, groups in match_map.items():
                while groups['pos'] and groups['neg']:
                    (groups['pos'].pop(0) + groups['neg'].pop(0)).reconcile()
        return True

    def _get_statistical_outliers(self, threshold_sigma=2.0):
        """ 
        FORENSIC ALGORITHM: Standard Deviation Outlier Detection (Point 2.2)
        Scans for movements that deviate significantly from the historical average.
        """
        import math
        lines = self.env['account.move.line'].search([('account_id', '=', self.id), ('parent_state', '=', 'posted')])
        if len(lines) < 10: return [] # Need enough data
        
        balances = [abs(l.balance) for l in lines]
        mean = sum(balances) / len(balances)
        
        # Pure Python Standard Deviation
        variance = sum((x - mean) ** 2 for x in balances) / len(balances)
        std_dev = math.sqrt(variance)
        
        limit = mean + (threshold_sigma * std_dev)
        outliers = lines.filtered(lambda l: abs(l.balance) > limit)
        return outliers

