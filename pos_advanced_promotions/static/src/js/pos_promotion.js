import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/store/pos_store";

/**
 * Advanced Mix & Match Bundle Engine - Odoo 18 (v2)
 *
 * يعمل على نماذج loyalty الأصلية مع حقول مخصصة:
 *   - loyalty.program.program_type = 'advanced_bundle'
 *   - loyalty.program.is_advanced_bundle = true
 *   - loyalty.program.bundle_price  (السعر الثابت للباقة - احتياطي)
 *   - loyalty.reward.reward_type    = 'fixed_price'
 *   - loyalty.reward.fixed_price    (السعر الثابت الفعلي للباقة)
 *
 * كيفية الإعداد في Odoo Backend:
 *   1. إنشاء برنامج loyalty من نوع "Advanced Mix & Match Bundle"
 *   2. فعّل خيار "Is Advanced Bundle"
 *   3. أضف قواعد (Rules) لكل فئة منتجات مع الكمية المطلوبة
 *   4. أضف جائزة (Reward) من نوع "Fixed Price for Bundle" مع السعر الثابت
 *   5. في إعدادات POS > تأكد من وجود "Discount Product" في قسم Pricing
 *
 * === التغييرات في النسخة الثانية (v2) ===
 *   - ربط المحرك بـ updateRewards بدلاً من addLineToCurrentOrder
 *     لضمان تحديث الخصم عند أي تغيير في السلة (كمية، حذف، باركود، عميل...)
 *   - حماية من الحلقة اللانهائية بعلامة _isApplyingBundles
 *   - تقسيم سطور الخصم حسب المجموعة الضريبية لحساب ضرائب صحيح
 *   - دعم تحويل وحدات القياس (UoM) باستخدام factor_inv
 *   - حماية أوامر المرتجعات (Refund)
 *   - إشعار Upselling للكاشير عند اقتراب اكتمال الباقة
 */
patch(PosStore.prototype, {

    /**
     * ربط محرك الباقات بنظام تحديث المكافآت التفاعلي في pos_loyalty.
     * دالة updateRewards تُستدعى تلقائياً عند:
     *   - أي تغيير في أسطر الطلب (عبر effect() التفاعلي)
     *   - تغيير الكمية عبر Keypad
     *   - حذف سطر من السلة
     *   - تغيير العميل أو قائمة الأسعار
     *   - مسح باركود منتج أو عميل أو كوبون
     */
    updateRewards() {
        super.updateRewards();
        // تشغيل محرك الباقات بعد انتهاء تحديث نظام الولاء الأساسي
        this._applyAdvancedBundlePromotions();
    },

    // =====================================================================
    //  أدوات مساعدة
    // =====================================================================

    /**
     * تحويل كمية من وحدة قياس المنتج إلى الوحدة المرجعية للفئة.
     * مثال: 250 جرام → 0.25 كيلوجرام
     *
     * @param {number} qty - الكمية بوحدة القياس الحالية
     * @param {Object} uom - كائن uom.uom من الـ models
     * @returns {number} الكمية بالوحدة المرجعية
     */
    _bundleConvertToReferenceUom(qty, uom) {
        if (!uom || uom.uom_type === "reference") {
            return qty;
        }
        // factor_inv = 1/factor = كم وحدة مرجعية في الوحدة الحالية
        return qty * (uom.factor_inv || 1);
    },

    /**
     * إنشاء مفتاح فريد لمجموعة الضرائب على سطر طلب.
     * يُستخدم لتجميع المنتجات حسب الضريبة.
     *
     * @param {Object} line - سطر الطلب
     * @returns {string} مفتاح مثل "5,14" (أرقام الضرائب مرتبة)
     */
    _bundleGetTaxGroupKey(line) {
        const taxes = line.product_id?.taxes_id || [];
        return taxes
            .map((t) => (t?.id ?? t))
            .sort((a, b) => a - b)
            .join(",");
    },

    // =====================================================================
    //  المحرك الرئيسي
    // =====================================================================

    /**
     * محرك حساب وتطبيق خصومات باقات Mix & Match.
     * يتم استدعاؤها من updateRewards عند أي تغيير في السلة.
     */
    _applyAdvancedBundlePromotions() {
        // --- حماية من الحلقة اللانهائية ---
        if (this._isApplyingBundles) return;
        this._isApplyingBundles = true;

        try {
            this._doApplyAdvancedBundlePromotions();
        } finally {
            this._isApplyingBundles = false;
        }
    },

    _doApplyAdvancedBundlePromotions() {
        const order = this.get_order();
        if (!order || order.finalized) return;

        // --- حماية المرتجعات ---
        if (order.lines.some((l) => l.refunded_orderline_id)) return;

        // الوصول للنماذج بالطريقة الصحيحة في Odoo 18
        const programStore = this.models["loyalty.program"];
        const ruleStore    = this.models["loyalty.rule"];
        const rewardStore  = this.models["loyalty.reward"];
        const productStore = this.models["product.product"];

        if (!programStore || !ruleStore || !rewardStore || !productStore) return;

        // تصفية برامج Advanced Bundle فقط
        const advancedPrograms = programStore.getAll().filter(
            (p) => p.program_type === "advanced_bundle" && p.is_advanced_bundle
        );

        if (!advancedPrograms.length) return;

        // --- حذف سطور الخصم القديمة التي أضفناها ---
        const oldRewardLines = order.lines.filter((l) => 
            l._isAdvancedBundleReward || 
            (l.customer_note && l.customer_note.includes("خصم باقة:"))
        );
        for (const line of oldRewardLines) {
            line.delete();
        }

        // متغير لتخزين معلومات الباقات الجزئية (للـ upselling)
        let bestPartialInfo = null;

        for (const program of advancedPrograms) {
            // قواعد وجوائز هذا البرنامج
            const rules = ruleStore.getAll().filter((r) => {
                const pid = r.program_id?.id ?? r.program_id;
                return pid === program.id;
            });

            const rewards = rewardStore.getAll().filter((r) => {
                const pid = r.program_id?.id ?? r.program_id;
                return pid === program.id && r.reward_type === "fixed_price";
            });

            if (!rules.length || !rewards.length) continue;

            const mainReward = rewards[0];
            // السعر الثابت: من الجائزة أو من البرنامج كاحتياطي
            const fixedBundlePrice =
                parseFloat(mainReward.fixed_price) || parseFloat(program.bundle_price) || 0;

            if (fixedBundlePrice <= 0) continue;

            // --- بناء خريطة الكميات المتاحة (بالوحدة المرجعية) ---
            const availableQty = {};
            for (const line of order.lines) {
                if (!line._isAdvancedBundleReward) {
                    const uom = line.product_id?.uom_id;
                    const rawQty = line.get_quantity();
                    availableQty[line.uuid] = this._bundleConvertToReferenceUom(rawQty, uom);
                }
            }

            let totalBundles = 0;
            let allMatchedItems = [];

            // البحث عن أكبر عدد من الباقات المكتملة
            let searching = true;
            while (searching) {
                // العرض يطبق مرة واحدة فقط في الفاتورة (حسب طلب العميل دائماً True)
                if (totalBundles >= 1) {
                    break;
                }

                let bundleItems = [];
                let bundleComplete = true;
                let firstUnmatchedRule = null;
                let firstUnmatchedRemainingQty = 0;

                for (const rule of rules) {
                    let qtyNeeded = parseFloat(rule.minimum_qty) || 1;
                    if (rule.uom_id) {
                        const uomModel = this.models["uom.uom"];
                        let ruleUom = null;
                        if (uomModel) {
                            let uomId = rule.uom_id;
                            if (typeof uomId === "object" && !Array.isArray(uomId)) {
                                uomId = uomId.id;
                            } else if (Array.isArray(uomId)) {
                                uomId = uomId[0];
                            }
                            ruleUom = uomModel.get(uomId);
                        }
                        if (ruleUom) {
                            qtyNeeded = this._bundleConvertToReferenceUom(qtyNeeded, ruleUom);
                        }
                    }
                    let itemsForRule = [];

                    // قائمة المنتجات المسموحة في هذه القاعدة
                    const ruleProductIds = new Set(
                        (rule.valid_product_ids || []).map((p) => p?.id ?? p)
                    );

                    // --- حساب إجمالي الكمية المتاحة للمنتجات المطابقة ---
                    let totalMatchingAvailable = 0;
                    for (const line of order.lines) {
                        if (line._isAdvancedBundleReward) continue;
                        const avail = availableQty[line.uuid] || 0;
                        if (avail <= 0.001) continue;

                        const product = line.product_id;
                        let matches = false;

                        if (rule.any_product) {
                            matches = true;
                        } else if (ruleProductIds.size > 0) {
                            matches = ruleProductIds.has(product.id);
                        } else {
                            matches = true;
                        }

                        if (matches) {
                            totalMatchingAvailable += avail;
                        }
                    }

                    // --- شرط التطابق التام (Exact Match) ---
                    // الكمية في السلة يجب أن تساوي الكمية المطلوبة بالظبط (لا زيادة ولا نقصان)
                    if (Math.abs(totalMatchingAvailable - qtyNeeded) > 0.001) {
                        bundleComplete = false;
                        if (!firstUnmatchedRule) {
                            firstUnmatchedRule = rule;
                            firstUnmatchedRemainingQty = Math.max(0, qtyNeeded - totalMatchingAvailable);
                        }
                        break;
                    }

                    for (const line of order.lines) {
                        if (line._isAdvancedBundleReward) continue;
                        const avail = availableQty[line.uuid] || 0;
                        if (avail <= 0.001) continue;

                        const product = line.product_id;
                        let matches = false;

                        if (rule.any_product) {
                            matches = true;
                        } else if (ruleProductIds.size > 0) {
                            matches = ruleProductIds.has(product.id);
                        } else {
                            matches = true;
                        }

                        if (matches) {
                            const take = Math.min(qtyNeeded, avail);
                            // نحتاج لتخزين الكمية الأصلية (قبل التحويل) لحساب السعر
                            const uom = product.uom_id;
                            const originalTake = uom && uom.uom_type !== "reference"
                                ? take / (uom.factor_inv || 1)
                                : take;
                            itemsForRule.push({ line, qty: take, originalQty: originalTake });
                            qtyNeeded -= take;
                            if (qtyNeeded <= 0.001) break;
                        }
                    }

                    if (qtyNeeded > 0.001) {
                        bundleComplete = false;
                        if (!firstUnmatchedRule) {
                            firstUnmatchedRule = rule;
                            firstUnmatchedRemainingQty = qtyNeeded;
                        }
                        break;
                    }
                    bundleItems.push(...itemsForRule);
                }

                if (bundleComplete && bundleItems.length > 0) {
                    totalBundles++;
                    allMatchedItems.push(...bundleItems);
                    for (const item of bundleItems) {
                        availableQty[item.line.uuid] -= item.qty;
                    }
                } else {
                    searching = false;

                    // --- حساب التقدم الجزئي للـ Upselling ---
                    if (totalBundles === 0 && firstUnmatchedRule && firstUnmatchedRemainingQty > 0.001) {
                        bestPartialInfo = {
                            programName: program.name,
                            remaining: firstUnmatchedRemainingQty,
                            rule: firstUnmatchedRule,
                        };
                    }
                }
            }

            if (totalBundles <= 0) continue;

            // --- حساب الخصم ---
            const actualTotal = allMatchedItems.reduce(
                (sum, item) => sum + item.line.get_unit_price() * item.originalQty,
                0
            );
            const targetTotal = fixedBundlePrice * totalBundles;
            const discountAmount = Math.max(0, actualTotal - targetTotal);

            if (discountAmount <= 0.01) continue;

            // --- جلب منتج الخصم من إعدادات POS أو من الجائزة ---
            let discProdId = mainReward.discount_line_product_id;
            discProdId = Array.isArray(discProdId) ? discProdId[0] : (discProdId?.id ?? discProdId);

            if (!discProdId) {
                const discProdConfig = this.config.discount_product_id || this.config.manual_discount_product_id;
                discProdId = Array.isArray(discProdConfig) ? discProdConfig[0] : (discProdConfig?.id ?? discProdConfig);
            }

            const discountProduct = discProdId ? productStore.get(discProdId) : null;

            if (!discountProduct) {
                console.warn(
                    "[AdvancedBundle] ⚠️ لم يُعثر على منتج الخصم!\n" +
                    "تأكد من ضبط 'Discount Product' في إعدادات نقطة البيع، أو في إعدادات البرنامج."
                );
                continue;
            }

            // ===================================================================
            //  تقسيم الخصم حسب المجموعة الضريبية
            // ===================================================================
            // تجميع المنتجات المطابقة حسب ضرائبها
            const taxGroups = {};
            for (const item of allMatchedItems) {
                const taxKey = this._bundleGetTaxGroupKey(item.line);
                if (!taxGroups[taxKey]) {
                    taxGroups[taxKey] = {
                        totalPrice: 0,
                        taxes: item.line.product_id?.taxes_id || [],
                        taxKey: taxKey,
                    };
                }
                taxGroups[taxKey].totalPrice += item.line.get_unit_price() * item.originalQty;
            }

            // حساب الحصة النسبية لكل مجموعة ضريبية وإنشاء سطور الخصم
            const taxGroupEntries = Object.values(taxGroups);
            let discountDistributed = 0;

            for (let i = 0; i < taxGroupEntries.length; i++) {
                const group = taxGroupEntries[i];
                const isLast = i === taxGroupEntries.length - 1;

                // الحصة النسبية من الخصم
                let groupDiscount;
                if (isLast) {
                    // آخر مجموعة تأخذ الباقي لتجنب أخطاء التقريب
                    groupDiscount = discountAmount - discountDistributed;
                } else {
                    const ratio = actualTotal > 0 ? group.totalPrice / actualTotal : 0;
                    groupDiscount = Math.round(ratio * discountAmount * 100) / 100;
                }
                discountDistributed += groupDiscount;

                if (groupDiscount <= 0.01) continue;

                // تحديد تسمية المجموعة الضريبية
                const taxLabel = group.taxes.length > 0
                    ? group.taxes.map((t) => t.name || t.id).join("+")
                    : "بدون ضريبة";

                // إنشاء سطر الخصم مباشرة (بدون addLineToCurrentOrder لتجنب الحلقة)
                const rewardLine = this.models["pos.order.line"].create({
                    order_id: order,
                    product_id: discountProduct,
                    price_unit: -groupDiscount,
                    qty: 1,
                    price_type: "manual",
                    tax_ids: group.taxes.map((tax) => ["link", tax]),
                    customer_note: `خصم باقة: ${program.name} (${totalBundles}×) [${taxLabel}]`,
                });

                // تعليم السطر كسطر خصم باقة
                if (rewardLine) {
                    rewardLine._isAdvancedBundleReward = true;
                }
            }

            // إعادة حساب بيانات الطلب بعد إضافة سطور الخصم
            order.recomputeOrderData();
        }

        // --- إشعار Upselling للكاشير ---
        if (bestPartialInfo && this.notification) {
            let uomName = "قطعة";
            let productDesc = "";
            const rule = bestPartialInfo.rule;
            if (rule) {
                // محاولة إيجاد اسم وحدة القياس من القاعدة أولاً
                if (rule.uom_id) {
                    if (typeof rule.uom_id === "object" && !Array.isArray(rule.uom_id)) {
                        uomName = rule.uom_id.name || rule.uom_id.display_name || uomName;
                    } else if (Array.isArray(rule.uom_id)) {
                        uomName = rule.uom_id[1] || uomName;
                    } else {
                        const uomModel = this.models["uom.uom"];
                        if (uomModel) {
                            const uomRec = uomModel.get(rule.uom_id);
                            if (uomRec && (uomRec.name || uomRec.display_name)) {
                                uomName = uomRec.name || uomRec.display_name;
                            }
                        }
                    }
                }

                const productStore = this.models["product.product"];
                const productIds = (rule.valid_product_ids || []).map((p) => p?.id ?? p);
                if (productIds.length > 0) {
                    // لو لم نجد وحدة القياس من القاعدة، نأخذها من أول منتج
                    if (uomName === "قطعة") {
                        const firstProd = productStore.get(productIds[0]);
                        if (firstProd && firstProd.uom_id) {
                            const uom = firstProd.uom_id;
                            if (typeof uom === "object" && !Array.isArray(uom)) {
                                uomName = uom.name || uom.display_name || uomName;
                            } else if (Array.isArray(uom)) {
                                uomName = uom[1] || uomName;
                            } else {
                                const uomModel = this.models["uom.uom"];
                                if (uomModel) {
                                    const uomRec = uomModel.get(uom);
                                    if (uomRec && (uomRec.name || uomRec.display_name)) {
                                        uomName = uomRec.name || uomRec.display_name;
                                    }
                                }
                            }
                        }
                    }

                    const productNames = [];
                    for (const id of productIds) {
                        const prod = productStore.get(id);
                        if (prod && prod.display_name) {
                            let name = prod.display_name;
                            if (name.includes(']')) {
                                name = name.split(']').pop().trim();
                            }
                            productNames.push(name);
                        }
                    }
                    if (productNames.length > 0) {
                        if (productNames.length <= 3) {
                            productDesc = ` من ${productNames.join(" أو ")}`;
                        } else {
                            productDesc = ` من ${productNames.slice(0, 3).join(" أو ")}...`;
                        }
                    }
                }
            }
            this.notification.add(
                `💡 أضف ${bestPartialInfo.remaining} ${uomName}${productDesc} لتفعيل عرض "${bestPartialInfo.programName}"`,
                { type: "warning", sticky: false }
            );
        }
    },
});
