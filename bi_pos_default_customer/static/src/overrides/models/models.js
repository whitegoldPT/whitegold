/** @odoo-module */

import { PosOrder } from "@point_of_sale/app/models/pos_order";
import { patch } from "@web/core/utils/patch";

patch(PosOrder.prototype, {

    setup() {
        super.setup(...arguments);
        var default_customer = this.config.res_partner_id;
        if(default_customer){
             var default_customer_by_id = default_customer.id;
             this.set_partner(default_customer_by_id);
        }
        else{
         this.set_partner(null);
        }
    },
    
});

