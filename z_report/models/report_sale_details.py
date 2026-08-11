# -*- coding: utf-8 -*-

from odoo import api, fields, models, _

class ReportZSaleDetails(models.AbstractModel):
    _name = 'report.z_report.report_z_saledetails'
    _inherit = 'report.point_of_sale.report_saledetails'
    _description = 'Z-Report Sale Details'

    @api.model
    def get_sale_details(self, date_start=False, date_stop=False, config_ids=False, session_ids=False, **kwargs):
        res = super(ReportZSaleDetails, self).get_sale_details(date_start, date_stop, config_ids, session_ids, **kwargs)
        
        if session_ids:
            sessions = self.env['pos.session'].search([('id', 'in', session_ids)])
            if sessions:
                # Add extra fields for the report
                opening_user = sessions[0].user_id
                closing_user = sessions[0].closing_user_id
                
                opening_employee_name = opening_user.name
                closing_employee_name = closing_user.name if closing_user else _('Not Closed Yet')
                
                # If HR module is installed, try to get the employee name
                if 'hr.employee' in self.env:
                    opening_employee = self.env['hr.employee'].sudo().search([('user_id', '=', opening_user.id)], limit=1)
                    if opening_employee:
                        opening_employee_name = opening_employee.name
                    
                    if closing_user:
                        closing_employee = self.env['hr.employee'].sudo().search([('user_id', '=', closing_user.id)], limit=1)
                        if closing_employee:
                            closing_employee_name = closing_employee.name

                res.update({
                    'opening_employee': opening_employee_name,
                    'closing_employee': closing_employee_name,
                    'starting_balance': sessions[0].cash_register_balance_start,
                    'ending_balance': sessions[0].cash_register_balance_end_real,
                })
        return res
