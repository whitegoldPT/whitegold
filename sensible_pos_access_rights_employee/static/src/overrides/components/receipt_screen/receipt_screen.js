/** @odoo-module */

import { ReceiptScreen } from "@point_of_sale/app/screens/receipt_screen/receipt_screen";
import { patch } from "@web/core/utils/patch";

patch(ReceiptScreen.prototype, {
    setup() {
        super.setup();
    },

    get hideNewOrderButton() {
        const employee = this.pos.get_cashier();
        return employee && employee.sbl_hide_pos_new_order_button || false;
    }
}); 