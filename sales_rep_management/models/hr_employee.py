import logging
from odoo import models, fields, api

_logger = logging.getLogger(__name__)

class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    work_email = fields.Char(string='Work Email', required=True)
    
    _sql_constraints = [
        ('work_email_unique', 'unique(work_email)', 'Work Email must be unique!')
    ]

    @api.constrains('work_email')
    def _check_work_email_unique(self):
        for employee in self:
            if employee.work_email:
                domain = [
                    ('work_email', '=ilike', employee.work_email),
                    ('id', '!=', employee.id)
                ]
                if self.search_count(domain):
                    raise models.ValidationError("The work email '%s' is already in use by another employee." % employee.work_email)
