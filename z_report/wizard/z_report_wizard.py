# -*- coding: utf-8 -*-

from odoo import fields, models

class ZReportWizard(models.TransientModel):
    _name = 'z.report.wizard'
    _description = 'Z-Report Wizard'

    pos_session_id = fields.Many2one('pos.session', string='Session', required=True)

    def generate_report(self):
        data = {
            'date_start': False, 
            'date_stop': False, 
            'config_ids': self.pos_session_id.config_id.ids, 
            'session_ids': self.pos_session_id.ids
        }
        return self.env.ref('z_report.action_report_z_session').report_action([], data=data)
