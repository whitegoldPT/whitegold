/** @odoo-module **/
import { SaleOrderLineProductField } from "@sale/js/sale_product_field";
import { Many2XAutocomplete } from "@web/views/fields/relational_utils";
import { patch } from "@web/core/utils/patch";
import {onWillStart, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation"; 
// import { RPCError } from "@web/core/network/rpc_service"; 

patch(SaleOrderLineProductField.prototype, {
    setup(){
        super.setup();
        this.access = useState({
            hide_prod_ext_link: false,
            hide_create: false,
            hide_createEdit: false,
        });
        onWillStart(async() => {
            let self = this;
            let res = await this.orm.call(
                "access.management",
                "ishide_sale_product_ext_link",
                [[]]
            );
            if(res){ 
                // FOR CREATE BUTTON
                this.props.canCreate = res.is_create;
                this.props.canQuickCreate = res.is_create;
                this.access.hide_create = res.is_create;
                // FOR EDIT BUTTON
                this.props.canCreateEdit = res.is_createEdit;
                this.access.hide_createEdit = res.is_createEdit;
                // FOR EXTERNAL LINK
                this.props.canOpen = res.is_open;
                if(!res.is_open){
                    this.access.hide_prod_ext_link = true;
                }
                // MODIFY STATE
                this.state.activeActions.create = res.is_create;
                this.state.activeActions.createEdit = res.is_createEdit;
            }
        });
    },
    get hasExternalButton() { 
        const res = super.hasExternalButton; 
        if(res && !this.access.hide_prod_ext_link){
            return true;
        }else if(res && this.access.hide_prod_ext_link){
            return false;
        } 
        else{
            return res
        }
    },
    get Many2XAutocompleteProps() { 
        const res = super.Many2XAutocompleteProps;
        if(res){
            res.activeActions.create = this.access.hide_create;
            res.activeActions.createEdit = this.access.hide_createEdit;
            res.quickCreate = this.access.hide_createEdit ? res.quickCreate : null;
        }
        return res;
    }
});