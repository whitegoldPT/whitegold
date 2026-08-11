# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

class AccountMove(models.Model):
    _inherit = 'account.move'

    risk_score = fields.Float(string='Risk Score', default=0.0, tracking=True)
    risk_level = fields.Selection([
        ('low', '🟢 منخفض'),
        ('medium', '🟡 متوسط'),
        ('high', '🔴 مرتفع'),
        ('critical', '☠️ حرج جداً')
    ], string='Risk Status', compute='_compute_risk_level', store=True)
    
    forensic_rule_ids = fields.Many2many('forensic.rule', string='Violated Rules')
    audit_status = fields.Selection([
        ('pending', '⚠️ بانتظار المراجعة'),
        ('approved', '✅ معتمد'),
        ('flagged', '🚩 محدد كمخاطرة'),
        ('fixed', '🔧 تم الإصلاح')
    ], string='Audit State', default='pending', tracking=True)
    forensic_diagnostic = fields.Text(string='سبب المشكلة')
    forensic_resolution = fields.Text(string='الحل المقترح')


    late_night_activity = fields.Boolean(compute='_compute_behavior', store=True)
    excessive_edits_flag = fields.Boolean(default=False)
    
    @api.depends('create_date')
    def _compute_behavior(self):
        for move in self:
            move.late_night_activity = move.create_date.hour < 5 if move.create_date else False

    @api.depends('risk_score')
    def _compute_risk_level(self):
        for move in self:
            if move.risk_score >= 100: move.risk_level = 'critical'
            elif move.risk_score >= 70: move.risk_level = 'high'
            elif move.risk_score >= 30: move.risk_level = 'medium'
            else: move.risk_level = 'low'

    def action_run_forensic_scan(self):
        """ 
        CORE ANALYTICS ENGINE 
        Integrates Statistical, Logic, and Pattern rules
        """
        for move in self:
            # 1. Reset diagnosis state
            move.line_ids.write({
                'diagnostic_reason': False,
                'suggested_action': False,
                'forensic_category': False
            })

            # 2. Hardcoded Forensic Algorithms (Phase 2 Roadmap)
            
            # A. Benford's Law (First Digit Analysis)
            is_benford_issue = move._check_benford_anomaly(move.amount_total)
            
            # B. Duplicate Bill Detection
            is_duplicate = move._check_duplicate_vendor_bill()
            
            # C. Lifecycle Tracing (Point 2.3 Roadmap)
            is_lifecycle_gap = move._check_lifecycle_integrity()
            
            # D. Link Analysis (Point 2.4 Roadmap)
            is_link_red_flag = move._check_employee_vendor_collision()

            # 3. Dynamic XML Rules Scan
            rules = self.env['forensic.rule'].search([('active', '=', True)])
            violated_rules = rules.filtered(lambda r: r.check_violation(move))
            
            total_score = sum(violated_rules.mapped('weight'))
            if is_benford_issue: total_score += 50
            if is_duplicate: total_score += 150
            if is_lifecycle_gap: total_score += 100
            if is_link_red_flag: total_score += 200 # Very high risk!

            # Initialize summaries
            diag_reasons = []
            diag_solutions = []

            if is_benford_issue: 
                diag_reasons.append("⚠️ انحراف إحصائي (Benford)")
                diag_solutions.append("تأكد من قيمة الفاتورة ومراجعة النسخة الورقية")
            if is_duplicate: 
                diag_reasons.append("🚩 فاتورة مكررة")
                diag_solutions.append("تحقق من رقم مرجع المورد وتكرار القيد")
            if is_lifecycle_gap: 
                diag_reasons.append("🔗 فجوة في الدورة المستندية")
                diag_solutions.append("تحقق من ارتباط أمر الشراء وصحة استلام الكميات")
            
            for rule in violated_rules:
                diag_reasons.append(f"🔍 {rule.name}")
                if rule.suggested_action:
                    diag_solutions.append(rule.suggested_action)

            move.write({
                'forensic_rule_ids': [(6, 0, violated_rules.ids)],
                'risk_score': total_score,
                'forensic_diagnostic': " / ".join(diag_reasons),
                'forensic_resolution': " / ".join(list(set(diag_solutions)))
            })
            
            # Primary Alert Logic
            if violated_rules or is_benford_issue or is_duplicate or is_lifecycle_gap:
                msg = ""
                if is_benford_issue: msg += "🔎 <b>فحص بنفورد:</b> شكل المبلغ مشبوه إحصائياً (تلاعب محتمل)"
                if is_duplicate: msg += "<br/>🚨 <b>تحذير:</b> فاتورة مورد مكررة محتملة"
                if is_lifecycle_gap: msg += "<br/>🔗 <b>فجوة تتبع:</b> دورة حياة المعاملة مكسورة (دفع بدون فاتورة أو استلام)"
                
                for rule in violated_rules:
                    msg += f"<br/>🔎 <b>تنبيه:</b> {rule.name}"
                
                # Only write forensic data on lines that have actual issues
                for line in move.line_ids:
                    line_has_issue = False
                    line_reason = ""
                    
                    # Check if this specific line triggers any rule
                    if line.account_id.account_type in ('asset_receivable', 'liability_payable') and not line.partner_id:
                        line_has_issue = True
                        line_reason = "نقص اسم الشريك في حساب ذمم"
                    elif line.account_id.account_type == 'asset_cash' and move.move_type == 'entry' and move.journal_id.type not in ('bank', 'cash'):
                        line_has_issue = True
                        line_reason = "قيد يدوي على حساب نقدية/بنك"
                    elif line.quantity > 0 and line.debit == 0 and line.credit == 0:
                        line_has_issue = True
                        line_reason = "كمية بدون قيمة مالية"
                    elif line.account_id.account_type in ('income', 'income_other') and move.move_type == 'entry':
                        line_has_issue = True
                        line_reason = "تسجيل إيرادات بقيد يدوي مباشر (تجاوز دورة الفوترة)"
                    elif move.move_type == 'in_refund' and move.reversed_entry_id and line.product_id:
                        orig_line = move.reversed_entry_id.line_ids.filtered(lambda l: l.product_id == line.product_id)
                        if orig_line and line.price_unit < orig_line[0].price_unit:
                            line_has_issue = True
                            line_reason = "سعر مرتجع المشتريات أقل من الفاتورة الأصلية (خسارة فارق)"
                    
                    if line_has_issue or diag_reasons:
                        line.write({
                            'diagnostic_reason': line_reason or " / ".join(diag_reasons[:2]),
                            'suggested_action': diag_solutions[0] if diag_solutions else 'راجع المستندات الورقية',
                            'audit_status': 'pending'
                        })
                    else:
                        # Clean lines stay clean
                        line.write({
                            'diagnostic_reason': False,
                            'suggested_action': False,
                            'audit_status': False
                        })

                if msg: move.message_post(body=msg)


    def _check_benford_anomaly(self, amount):
        if not amount or amount <= 0:
            return False
        try:
            digits = str(abs(amount)).lstrip('0.')
            if not digits:
                return False
            first_digit = int(digits[0])
            return first_digit in (7, 8, 9) and amount > 1000
        except (IndexError, ValueError):
            return False

    def _check_duplicate_vendor_bill(self):
        if self.move_type != 'in_invoice' or not self.ref or not self.partner_id:
            return False
        return bool(self.search_count([
            ('id', '!=', self.id),
            ('move_type', '=', 'in_invoice'),
            ('partner_id', '=', self.partner_id.id),
            ('ref', '=', self.ref),
            ('state', '!=', 'cancel')
        ]))

    def _check_lifecycle_integrity(self):
        """ 
        FORENSIC TRACING: Detects broken chains in business cycle 
        Checks PO -> Picking -> Bill -> Payment 
        """
        if self.move_type in ('in_invoice', 'in_refund'):
            # A. Check for PO Linkage (Common Fraud: Direct Bill without PO)
            if not self.invoice_line_ids.mapped('purchase_line_id'):
                return True
            
            # B. Check for Quantity Discrepancy
            for line in self.invoice_line_ids.filtered(lambda l: l.product_id):
                po_line = line.purchase_line_id
                if po_line:
                    received_qty = po_line.qty_received
                    billed_qty = line.quantity
                    if self.move_type == 'in_invoice' and billed_qty > received_qty:
                        return True
                    # C. Check for Refund Discrepancy (Returning more than purchased)
                    if self.move_type == 'in_refund' and abs(billed_qty) > po_line.product_qty:
                        return True

            
            # C. Check if linked Pickings are validated
            purchase_orders = self.invoice_line_ids.mapped('purchase_line_id.order_id')
            pickings = purchase_orders.mapped('picking_ids').filtered(lambda p: p.picking_type_code == 'incoming')
            if pickings and all(p.state != 'done' for p in pickings):
                return True # Risk: Billed while stock is still pending
        return False

    def _check_employee_vendor_collision(self):
        """ 
        FORENSIC LINK ANALYSIS (Point 2.4)
        Detects shared Bank Account, Phone, or Email between Vendor and Employees 
        """
        if self.move_type != 'in_invoice' or not self.partner_id:
            return False
        
        vendor = self.partner_id
        # Get all internal users' partners
        internal_partners = self.env['res.users'].search([('share', '=', False)]).mapped('partner_id')
        
        # Check Phone collision
        if vendor.phone and vendor.phone in internal_partners.mapped('phone'): return True
        if vendor.email and vendor.email in internal_partners.mapped('email'): return True
        
        # Check Bank Account collision
        vendor_banks = vendor.bank_ids.mapped('acc_number')
        if vendor_banks:
            internal_banks = internal_partners.mapped('bank_ids.acc_number')
            if any(b in internal_banks for b in vendor_banks): return True
            
        return False


    def action_post(self):
        if not self.env.context.get('skip_forensic'):
            for move in self:
                move.action_run_forensic_scan()
                if move.risk_level == 'critical':
                    raise UserError(_("🛡️ Forensic Block: High-risk anomaly detected. Post denied."))
        return super(AccountMove, self).action_post()
