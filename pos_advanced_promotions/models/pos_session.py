from odoo import models, api


class LoyaltyProgram(models.Model):
    _inherit = 'loyalty.program'

    @api.model
    def _load_pos_data_fields(self, config_id):
        """Extend POS data fields to include our custom bundle fields."""
        params = super()._load_pos_data_fields(config_id)
        params += ['bundle_price', 'is_advanced_bundle', 'bundle_apply_once']
        return params


class LoyaltyReward(models.Model):
    _inherit = 'loyalty.reward'

    @api.model
    def _load_pos_data_fields(self, config_id):
        """Extend POS data fields to include the fixed_price field."""
        params = super()._load_pos_data_fields(config_id)
        params += ['fixed_price']
        return params


class LoyaltyRule(models.Model):
    _inherit = 'loyalty.rule'

    @api.model
    def _load_pos_data_fields(self, config_id):
        """Extend POS data fields to include our custom uom_id field."""
        params = super()._load_pos_data_fields(config_id)
        params += ['uom_id']
        return params

