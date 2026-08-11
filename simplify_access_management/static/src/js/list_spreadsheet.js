/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ListController } from "@web/views/list/list_controller";
import { useState } from "@odoo/owl";
import { onMounted } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

patch(ListController.prototype, {
    setup() {
        if (typeof super.setup === "function") {
            super.setup();
        }
        try {
            this.orm = useService("orm");
        } catch (e) {
            console.debug('access_management: orm service not available via useService on ListController', e);
        }
        this._accessSpreadsheet = useState({ hideInsert: false });
        onMounted(async () => {
            try {
                if (this?.env?.config?.actionType == "ir.actions.act_window") {
                    if (!this.orm) {
                        console.debug('access_management: orm service missing on ListController, skipping backend check');
                    } else {
                        const res = await this.orm.call(
                            "access.management",
                            "is_spread_sheet_available",
                            [1, this?.env?.config?.actionType, this?.env?.config?.actionId]
                        );
                        this._accessSpreadsheet.hideInsert = !!res;
                    }
                }
            } catch (e) {
                console.error("access_management: failed to fetch spreadsheet availability", e);
            }
        });
        try {
            const protoGetter = this.getStaticActionMenuItems.bind(this);
            this.getStaticActionMenuItems = function() {
                const menuItems = protoGetter(...arguments);
                try {
                    if (menuItems && menuItems.insert) {
                        const originalIsAvailable = menuItems.insert.isAvailable || (() => true);
                        menuItems.insert.isAvailable = () => {
                            try {
                                return originalIsAvailable() && !this._accessSpreadsheet.hideInsert;
                            } catch (e) {
                                return !this._accessSpreadsheet.hideInsert;
                            }
                        };
                    } 

                    // else {
                    //     for (const [key, item] of Object.entries(menuItems || {})) {
                    //         if (!item) continue;
                    //         const desc = (item.description || "").toString().toLowerCase();
                    //         const icon = (item.icon || "").toString();
                    //         if (desc.includes('insert in spreadsheet') || icon === 'oi oi-view-list') {
                    //             const originalIsAvailable = item.isAvailable || (() => true);
                    //             item.isAvailable = () => {
                    //                 try {
                    //                     return originalIsAvailable() && !this._accessSpreadsheet.hideInsert;
                    //                 } catch (e) {
                    //                     return !this._accessSpreadsheet.hideInsert;
                    //                 }
                    //             };
                    //         }
                    //     }
                    // }
                } catch (e) {
                    console.error('access_management: error wrapping menu items', e);
                }
                return menuItems;
            };
        } catch (e) {
            console.error('access_management: failed to wrap getStaticActionMenuItems on instance', e);
        }
    },

    getStaticActionMenuItems() {
        const menuItems = super.getStaticActionMenuItems(...arguments);
        if (menuItems && menuItems.insert) {
            const originalIsAvailable = menuItems.insert.isAvailable || (() => true);
            menuItems.insert.isAvailable = () => {
                try {
                    return originalIsAvailable() && !this._accessSpreadsheet.hideInsert;
                } catch (e) {
                    return !this._accessSpreadsheet.hideInsert;
                }
            };
        }
        return menuItems;
    },
});
