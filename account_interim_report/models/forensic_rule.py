# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.tools.safe_eval import safe_eval

class ForensicRule(models.Model):
    _name = 'forensic.rule'
    _description = 'Forensic Integrity Rule'

    name = fields.Char(string='Rule Name', required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    category = fields.Selection([
        ('fraud', 'Fraud & Embezzlement'),
        ('compliance', 'Policy Compliance'),
        ('accuracy', 'Data Accuracy'),
        ('efficiency', 'Process Efficiency'),
        ('behavioral', 'Behavioral Analysis')
    ], required=True)
    
    severity = fields.Selection([
        ('low', 'Low'), ('medium', 'Medium'), ('high', 'High'), ('critical', 'Critical')
    ], default='medium')
    
    weight = fields.Integer(string='Risk Weight', default=10, help="Score contribution when rule is violated")
    action_type = fields.Selection([
        ('warn', 'Log Warning'),
        ('approve', 'Require Manager Approval'),
        ('block', 'Prevent Transaction')
    ], default='warn')

    rule_type = fields.Selection([
        ('python', 'Python Expression'),
        ('domain', 'Domain Filter')
    ], default='python')
    
    python_code = fields.Text(string='Python Analysis Code')
    domain = fields.Text(string='Domain Filter')
    description = fields.Text(string='Auditor Insight (Diagnostic)')

    suggested_action = fields.Text(string='Remediation Step')

    def check_violation(self, move):
        """ 
        PHASE 1 FIX: Safe eval context with datetime support
        Ensures complex rules don't crash.
        """
        self.ensure_one()
        try:
            from datetime import date, datetime, timedelta
            eval_context = {
                'move': move,
                'lines': move.line_ids,
                'env': self.env,
                'fields': fields,
                'date': date,
                'datetime': datetime,
                'timedelta': timedelta,
                'result': False
            }
            safe_eval(self.python_code, eval_context, mode='exec', nocopy=True)
            return eval_context.get('result', False)
        except Exception:
            return False
