/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { PartnerList } from "@point_of_sale/app/screens/partner_list/partner_list";

// Module-level cache so we only do the RPC call once per POS session
let _canCreateCustomerCache = null;
let _canCreateCustomerPromise = null;

async function _fetchCanCreateCustomer(orm) {
    if (_canCreateCustomerCache !== null) {
        return _canCreateCustomerCache;
    }
    if (_canCreateCustomerPromise) {
        return _canCreateCustomerPromise;
    }
    _canCreateCustomerPromise = (async () => {
        try {
            const result = await orm.call(
                "res.users",
                "pos_check_can_create_customer",
                []
            );
            _canCreateCustomerCache = !!result;
        } catch (e) {
            console.warn(
                "pos_customer_create_access: permission check RPC failed, defaulting to allow",
                e
            );
            // Fail-open on RPC error — server-side block remains active
            _canCreateCustomerCache = true;
        }
        return _canCreateCustomerCache;
    })();
    return _canCreateCustomerPromise;
}

function _getOrm(component) {
    if (component.pos && component.pos.orm) {
        return component.pos.orm;
    }
    if (component.env && component.env.services && component.env.services.orm) {
        return component.env.services.orm;
    }
    return null;
}

function _showAccessDenied(component) {
    try {
        const dialog =
            component.dialog ||
            (component.env && component.env.services && component.env.services.dialog);
        if (dialog && typeof dialog.add === "function") {
            dialog.add(AlertDialog, {
                title: _t("Access Denied"),
                body: _t(
                    "You do not have permission to create new customers from " +
                    "Point of Sale. Please contact your administrator."
                ),
            });
        } else {
            alert(_t("Access Denied: You cannot create new customers from POS."));
        }
    } catch (e) {
        console.warn("pos_customer_create_access: could not show dialog", e);
    }
}

// Patch all known method names that can trigger new-partner creation in
// Odoo 18 PartnerList. Different builds may use different names.
const _patchObj = {
    async createPartner() {
        const orm = _getOrm(this);
        if (orm) {
            const allowed = await _fetchCanCreateCustomer(orm);
            if (!allowed) {
                _showAccessDenied(this);
                return;
            }
        }
        return super.createPartner(...arguments);
    },

    async clickNewPartner() {
        const orm = _getOrm(this);
        if (orm) {
            const allowed = await _fetchCanCreateCustomer(orm);
            if (!allowed) {
                _showAccessDenied(this);
                return;
            }
        }
        if (typeof super.clickNewPartner === "function") {
            return super.clickNewPartner(...arguments);
        }
    },

    async addNewPartner() {
        const orm = _getOrm(this);
        if (orm) {
            const allowed = await _fetchCanCreateCustomer(orm);
            if (!allowed) {
                _showAccessDenied(this);
                return;
            }
        }
        if (typeof super.addNewPartner === "function") {
            return super.addNewPartner(...arguments);
        }
    },

    async saveChanges(processedChanges) {
        const isNew =
            !processedChanges ||
            !processedChanges.id ||
            processedChanges.id < 0;
        if (isNew) {
            const orm = _getOrm(this);
            if (orm) {
                const allowed = await _fetchCanCreateCustomer(orm);
                if (!allowed) {
                    _showAccessDenied(this);
                    return;
                }
            }
        }
        if (typeof super.saveChanges === "function") {
            return super.saveChanges(...arguments);
        }
    },
};

if (PartnerList && PartnerList.prototype) {
    patch(PartnerList.prototype, _patchObj);
    console.log(
        "pos_customer_create_access: PartnerList prototype patched successfully"
    );
} else {
    console.warn(
        "pos_customer_create_access: PartnerList not found — frontend block " +
            "won't be applied. Server-side block remains active."
    );
}
