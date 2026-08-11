from odoo import models, fields, api


class LoyaltyProgram(models.Model):
    _inherit = 'loyalty.program'

    program_type = fields.Selection(selection_add=[
        ('advanced_bundle', 'Advanced Mix & Match Bundle')
    ], ondelete={'advanced_bundle': 'set default'})

    is_advanced_bundle = fields.Boolean('Is Advanced Bundle', default=False)
    bundle_price = fields.Float('Fixed Bundle Price', default=0.0)
    bundle_apply_once = fields.Boolean('تطبيق مرة واحدة فقط (لكل فاتورة)', default=True)

    def _compute_coupon_count_display(self):
        """
        Override to avoid KeyError when program_type = 'advanced_bundle'.
        Odoo's original method uses dict[key] without .get(), which crashes
        for any unknown program_type.
        """
        program_items_name = {
            'coupons': 'Coupons',
            'promotions': 'Promotions',
            'loyalty': 'Loyalty Cards',
            'next_order_coupons': 'Next Order Coupons',
            'buy_x_get_y': 'Rewards',
            'advanced_bundle': 'Bundles',
            'ewallet': 'eWallets',
        }
        for program in self:
            count = program.coupon_count or 0
            label = program_items_name.get(program.program_type, 'Items')
            program.coupon_count_display = "%i %s" % (count, label)


class LoyaltyRule(models.Model):
    _inherit = 'loyalty.rule'

    minimum_qty = fields.Float(
        'Quantity',
        default=1.0,
        digits='Product Unit of Measure'
    )

    uom_id = fields.Many2one(
        'uom.uom',
        string='Unit of Measure',
        required=True
    )
    


class LoyaltyReward(models.Model):
    _inherit = 'loyalty.reward'

    reward_type = fields.Selection(selection_add=[
        ('fixed_price', 'Fixed Price for Bundle')
    ], ondelete={'fixed_price': 'set default'})

    fixed_price = fields.Float('Fixed Bundle Price', default=0.0)
