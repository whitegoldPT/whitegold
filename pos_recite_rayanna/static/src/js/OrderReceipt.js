/** @odoo-module **/

import { OrderReceipt } from "@point_of_sale/app/screens/receipt_screen/receipt/order_receipt";
import { PrinterService } from "@point_of_sale/app/printer/printer_service";
import { patch } from "@web/core/utils/patch";

patch(OrderReceipt.prototype, {
    get processedLines() {
        // console.log("line: ")
        // console.log(this.props.data)
        return (this.props.data.orderlines || []).map((line, index) => {
            // console.log("line price_without_discount: ")
            // console.log(line.price_without_discount)
            // Odoo 18 POS receipt data uses different field names:
            //   price_display  → formatted total price string  e.g. "25.00"
            //   unitPrice      → formatted unit price string
            //   price_with_tax → raw numeric total (fallback)
            const rawTotal = typeof line.price_with_tax === 'number'
                ? line.price_with_tax
                : parseFloat(String(line.price_display || line.price || "0").replace(/[^\d.\-]/g, "")) || 0;
            const rawUnit = typeof line.price_unit === 'number'
                ? line.price_unit
                : parseFloat(String(line.unitPrice || "0").replace(/[^\d.\-]/g, "")) || 0;
            return {
                ...line,
                // Guaranteed unique key even when line.id is absent
                _key: line.cid || line.id || String(index),
                price_num: rawTotal,
                unit_price_num: rawUnit,
                discount: parseFloat(line.discount) || 0,
                price_without_discount: parseFloat(String(line.price_without_discount || "0").replace(/[^\d.\-]/g, "")) || (rawUnit / (1 - (parseFloat(line.discount) || 0) / 100)),
            };
        });
    },
    get hasAnyDiscount() {
        return (this.props.data.orderlines || []).some(line => (parseFloat(line.discount) || 0) > 0);
    },
    get englishDate() {
        return new Date().toLocaleString('en-US', {
            year: 'numeric',
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
            hour12: true
        });
    }
});

/**
 * Fix Odoo 18 bug: render_service.js passes `ref.el.firstChild` as `el` to
 * applyWhenMounted, which does `[...el.classList]`. When OWL inserts a text or
 * comment node before the actual receipt div, `el` has no classList → crash.
 * Walk siblings to find the first real Element (nodeType 1) before delegating.
 */
patch(PrinterService.prototype, {
    printWeb(el) {
        console.log("test printWeb: ")
        console.log(el)
        let safeEl = el;
        while (safeEl && safeEl.nodeType !== Node.ELEMENT_NODE) {
            safeEl = safeEl.nextSibling;
        }
        return super.printWeb(safeEl || el);
    },
});
