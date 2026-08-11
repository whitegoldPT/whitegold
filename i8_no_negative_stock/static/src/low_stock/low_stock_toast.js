/** @odoo-module **/

import { registry } from "@web/core/registry";
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";

console.log("[i8_low_stock] FILE LOADED (pos bundle)");

// ------- helpers -------
function debounce(fn, wait) {
    let t;
    return function (...args) {
        clearTimeout(t);
        t = setTimeout(() => fn.apply(this, args), wait);
    };
}

function needsMapFromOrder(order) {
    const map = {};
    if (!order || !order.get_orderlines) return map;
    for (const line of order.get_orderlines()) {
        const product = line.get_product && line.get_product();
        const qty = line.get_quantity && line.get_quantity();
        if (!product || !qty || qty <= 0) continue;
        map[product.id] = (map[product.id] || 0) + qty;
    }
    return map;
}

function signatureOf(order) {
    const lines = order?.get_orderlines ? order.get_orderlines() : [];
    return lines.map(l => {
        const p = l.get_product && l.get_product();
        const q = l.get_quantity && l.get_quantity();
        return p ? `${p.id}:${q}` : "";
    }).join("|");
}

async function runCheck(env, pos) {
    const state = getSharedState(pos);
    const order = pos.get_order && pos.get_order();
    const config = pos.config;
    if (!config || !config.low_stock_alert_enabled) return;

    const needs = needsMapFromOrder(order);
    if (!Object.keys(needs).length) return;

    const results = await env.services.orm.call(
        "pos.session",
        "i8_check_low_stock",
        [pos.session.id, needs],
        {}
    );

    const COOLDOWN_MS = 60_000;
    const nowTs = Date.now();

    for (const r of results || []) {
        const pid = r.product_id;
        const remaining = typeof r.remaining === "number" ? r.remaining : 0;

        if (!r.threshold_hit) {
            delete state.lastNotifiedRemaining[pid];
            delete state.lastToastAt[pid];
            continue;
        }

        const prevRemaining = state.lastNotifiedRemaining[pid];
        const lastTs = state.lastToastAt[pid] || 0;

        const droppedFurther = prevRemaining === undefined || remaining < prevRemaining - 1e-6;
        const cooledDown = nowTs - lastTs >= COOLDOWN_MS;

        if (droppedFurther && cooledDown) {
            env.services.notification.add(
                _t("%(name)s is low on stock. Remaining after this order: %(rem)s", {
                    name: r.display_name,
                    rem: remaining.toFixed(2),
                }),
                { type: "warning", sticky: true }
            );
            state.lastNotifiedRemaining[pid] = remaining;
            state.lastToastAt[pid] = nowTs;
        }
    }
}

function getSharedState(pos) {
    if (!pos.i8_low_stock_state) {
        pos.i8_low_stock_state = {
            lastSig: "",
            lastNotifiedRemaining: {},
            lastToastAt: {},
        };
    }
    return pos.i8_low_stock_state;
}

function installWatcherOnScreen(ScreenClass, screenName) {
    const OrigSetup = ScreenClass.prototype.setup;
    const OrigWillUnmount = ScreenClass.prototype.willUnmount;

    patch(ScreenClass.prototype, {
        setup() {
            if (OrigSetup) OrigSetup.call(this);
            const pos = this.pos;
            const state = getSharedState(pos);

            const debounced = debounce(() => runCheck(this.env, pos), 300);

            this._i8_interval = setInterval(() => {
                try {
                    const order = pos.get_order && pos.get_order();
                    const sig = signatureOf(order);
                    if (sig !== state.lastSig) {
                        state.lastSig = sig;
                        debounced();
                    }
                } catch { /* ignore */ }
            }, 600);
        },
        willUnmount() {
            if (this._i8_interval) clearInterval(this._i8_interval);
            if (OrigWillUnmount) OrigWillUnmount.call(this);
        },
    });
}

const PaymentScreen = registry.category("pos_screens").get("PaymentScreen");
const ProductScreen = registry.category("pos_screens").get("ProductScreen");

if (PaymentScreen) {
    installWatcherOnScreen(PaymentScreen, "Payment");
} else {
    console.warn("[i8_low_stock] PaymentScreen not found in registry");
}
if (ProductScreen) {
    installWatcherOnScreen(ProductScreen, "Product");
} else {
    console.warn("[i8_low_stock] ProductScreen not found in registry");
}