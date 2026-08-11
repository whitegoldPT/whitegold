from odoo import fields, models, api, _
from odoo.http import request

class access_management(models.Model):
    _inherit = 'access.management'

    def ishide_sale_product_ext_link(self):
        # Return True if hide / return False if not hide
        """
        is_createEdit: for edit link hide
        is_open :for external link hide
        is_create :for create link hide
        """
        vals = {
        'is_open' : True,
        'is_create' : True,
        'is_createEdit' : True,
        }
        hide_field_obj = self.env['hide.field'].sudo()
        hide_field_id = hide_field_obj.search(
        [('access_management_id.company_ids', 'in', self.env.company.id),
        ('model_id.model', '=', 'sale.order.line'), ('access_management_id.active', '=', True),
        ('access_management_id.user_ids', 'in', self._uid),
        ('external_link','=',True)],limit=1)

        if hide_field_id:
            if self.env['ir.model.fields'].sudo().search([('name','in',['create_option','edit_option'])]):
                if hide_field_id.create_option:
                    vals.update({
                    'is_open' : False,
                    'is_create' : False,
                    })
                if hide_field_id.edit_option:
                    vals.update({
                    'is_open' : False,
                    'is_create': False,
                    'is_createEdit' : False,
                    })
              
            else:
                vals.update({
                'is_open' : False,
                'is_create' : False,
                'is_createEdit' : False,
                })
        return vals


   