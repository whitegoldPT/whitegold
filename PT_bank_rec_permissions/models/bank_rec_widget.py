from odoo import models
from odoo.exceptions import AccessError

class BankRecWidget(models.Model):
    _inherit = "bank.rec.widget"

    def _js_action_validate(self):
        if not self.env.user.has_group("PT_bank_rec_permissions.group_bank_rec_validate"):
            raise AccessError("You are not allowed to validate reconciliation.")
        return super()._js_action_validate()

    def _js_action_reset(self):
        if not self.env.user.has_group("PT_bank_rec_permissions.group_bank_rec_validate"):
            raise AccessError("You are not allowed to reset reconciliation.")
        return super()._js_action_reset()

    def _js_action_set_as_checked(self):
        if not self.env.user.has_group("PT_bank_rec_permissions.group_bank_rec_validate"):
            raise AccessError("You are not allowed to set transactions as checked.")
        return super()._js_action_set_as_checked()