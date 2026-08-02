/** @odoo-module **/

import { registry } from "@web/core/registry";
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";

const PaymentScreen = registry.category("pos_screens").get("PaymentScreen");
const _origValidateOrder = PaymentScreen.prototype.validateOrder;

patch(PaymentScreen.prototype, {
    async validateOrder(isForceValidate) {
        try {
            return await _origValidateOrder.call(this, isForceValidate);
        } catch (e) {
            this.env.services.notification.add(
                _t(e?.message || "Insufficient stock for one or more items."),
                { type: "danger" }
            );
            throw e;
        }
    },
});
