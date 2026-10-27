from odoo import api, fields, models, _
from datetime import timedelta

class ConsumptionForensicAudit(models.Model):
    _name = "consumption.forensic.audit"
    _description = "Consumption Forensic Audit Log"
    _order = "create_date desc"

    name = fields.Char(string="Anomaly Description", required=True)
    request_id = fields.Many2one("consumption.request", string="Linked Request")
    employee_id = fields.Many2one("hr.employee", related="request_id.employee_id", store=True)
    audit_type = fields.Selection([
        ('duplicate', 'Potential Duplicate'),
        ('abnormal_qty', 'Abnormal Quantity'),
        ('stuck_transit', 'Stuck in Transit'),
        ('unauthorized', 'Unauthorized Approval Pattern')
    ], string="Anomaly Type", required=True)
    risk_level = fields.Selection([
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High')
    ], string="Risk Level", default='low')
    details = fields.Text(string="Technical Details")
    state = fields.Selection([
        ('new', 'New'),
        ('verified', 'Verified Anomaly'),
        ('false_positive', 'False Positive'),
        ('resolved', 'Resolved')
    ], default='new', string="Audit Status")

    def action_verify(self):
        self.write({'state': 'verified'})

    def action_dismiss(self):
        self.write({'state': 'false_positive'})

class ConsumptionRequest(models.Model):
    _inherit = "consumption.request"

    audit_log_ids = fields.One2many("consumption.forensic.audit", "request_id", string="Audit Alerts")
    risk_score = fields.Selection([
        ('0', 'Normal'),
        ('1', 'Low Risk'),
        ('2', 'Medium Risk'),
        ('3', 'High Risk')
    ], compute="_compute_risk_score", string="Risk Level", store=True, default='0')

    @api.depends('audit_log_ids')
    def _compute_risk_score(self):
        for rec in self:
            score = 0
            for audit in rec.audit_log_ids:
                if audit.risk_level == 'high': score += 50
                elif audit.risk_level == 'medium': score += 20
                else: score += 5
            
            # Map score to priority stars
            if score >= 50: rec.risk_score = '3'
            elif score >= 20: rec.risk_score = '2'
            elif score > 0: rec.risk_score = '1'
            else: rec.risk_score = '0'

    def action_submit(self):
        res = super().action_submit()
        self._run_forensic_check()
        return res

    def _run_forensic_check(self):
        """Intelligent background auditing for consumption requests"""
        for rec in self:
            # 1. Duplicate Check (Same product to same employee within 3 days)
            for line in rec.line_ids:
                recent_requests = self.env['consumption.request.line'].search([
                    ('employee_id', '=', rec.employee_id.id),
                    ('product_id', '=', line.product_id.id),
                    ('request_id.state', 'in', ['approved', 'dispatched', 'done']),
                    ('id', '!=', line.id),
                    ('create_date', '>=', fields.Datetime.now() - timedelta(days=3))
                ])
                if recent_requests:
                    self.env['consumption.forensic.audit'].create({
                        'name': _("Potential Duplicate for %s") % line.product_id.display_name,
                        'request_id': rec.id,
                        'audit_type': 'duplicate',
                        'risk_level': 'medium',
                        'details': _("Employee requested this product %d times in the last 72 hours.") % len(recent_requests)
                    })

            # 2. Abnormal Quantity Check (Simple 3x average check)
            # This is a placeholder for more complex logic
            for line in rec.line_ids:
                if line.product_qty > 50: # Arbitrary threshold for demo
                    self.env['consumption.forensic.audit'].create({
                        'name': _("Abnormal Quantity: %s") % line.product_id.display_name,
                        'request_id': rec.id,
                        'audit_type': 'abnormal_qty',
                        'risk_level': 'high',
                        'details': _("Requested quantity (%f) is significantly higher than safety stock or expected use.") % line.product_qty
                    })
