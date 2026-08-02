# -*- coding: utf-8 -*-
from odoo import models, fields, api

class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    diagnostic_reason = fields.Char(string='Detected Anomaly', readonly=True)
    suggested_action = fields.Char(string='Correction Recommendation', readonly=True)
    audit_note = fields.Text(string='Audit Notes')
    forensic_category = fields.Selection([
        ('purchase', 'مشتريات'), ('sale', 'مبيعات'), 
        ('inventory', 'مخازن'), ('manufacturing', 'تصنيع'), ('general', 'عام')
    ], string='Forensic Category', readonly=True, index=True)
    
    risk_score = fields.Float(related='move_id.risk_score', readonly=True, index=True)
    risk_level = fields.Selection(related='move_id.risk_level', readonly=True)
    is_cross_department = fields.Boolean(string='Cross-Dept', default=False)

    audit_status = fields.Selection([
        ('pending', '⚠️ معلق'), ('approved', '✅ تم الفحص'), 
        ('fixed', '🔧 تم الإصلاح'), ('disputed', '⚖️ متنازع عليه')
    ], string='Audit State', tracking=True, index=True)

    def action_smart_fix(self):
        self.ensure_one()
        return {
            'name': 'مركز الإصلاح الذكي',
            'type': 'ir.actions.act_window',
            'res_model': 'account.interim.correction.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_line_id': self.id}
        }

    def action_refresh_line_diagnosis(self):
        for line in self:
            line.move_id.action_run_forensic_scan()
        return True

    def action_mark_as_fixed(self):
        self.write({'audit_status': 'fixed'})
        return True

    def action_view_golden_thread(self):
        self.ensure_one()
        wizard = self.env['forensic.thread.wizard'].create({
            'line_id': self.id,
        })
        return wizard.action_trace_thread()


    def action_run_forensic_scan(self):
        """ Allow running scan from move line list """
        return self.mapped('move_id').action_run_forensic_scan()

    def action_universal_deep_scrub(self):
        """ Passthrough to engine """
        return self.env['account.interim.report'].action_run_forensic_scan()

    @api.model
    def _cron_automated_forensic_scan(self):
        """ Called by the nightly cron job to scan recent posted moves """
        import logging
        _logger = logging.getLogger(__name__)
        try:
            self.env['account.interim.report'].action_run_forensic_scan()
            _logger.info('Forensic Engine: Nightly scan completed successfully.')
        except Exception as e:
            _logger.error('Forensic Engine: Nightly scan failed: %s', str(e))
