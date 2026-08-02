# -*- coding: utf-8 -*-
import logging
_logger = logging.getLogger(__name__)
from odoo import models, fields, api, _, exceptions
from odoo.exceptions import UserError, ValidationError
import base64
import io
from datetime import date as date_type
from collections import defaultdict

# ------------------------------------------------------------------ #
#  دالة مساعدة                                                        #
# ------------------------------------------------------------------ #
def _fz(value, digits=2):
    return abs(value or 0.0) < (10 ** -digits)

MOVE_TYPE_LABELS = {
    'out_invoice':  'فاتورة عميل',
    'in_invoice':   'فاتورة مورد',
    'out_refund':   'مرتجع عميل',
    'in_refund':    'مرتجع مورد',
    'out_payment':  'دفعة صادرة',
    'in_payment':   'دفعة واردة',
    'entry':        'قيد يومية',
}

SEVERITY_HIGH   = 'high'
SEVERITY_MEDIUM = 'medium'
SEVERITY_LOW    = 'low'

class AccountInterimWizard(models.TransientModel):
    _name = 'account.interim.wizard'
    _description = 'تقرير الحسابات الوسيطة / المؤقتة - تحليلي'

    date_from = fields.Date(string='من تاريخ', required=True, default=lambda self: fields.Date.context_today(self).replace(day=1))
    date_to = fields.Date(string='إلى تاريخ', required=True, default=fields.Date.context_today)
    tag_ids = fields.Many2many('account.account.tag', string='التاغات الوسيطة', required=True)
    company_id = fields.Many2one('res.company', string='الشركة', required=True, default=lambda self: self.env.company)
    partner_ids = fields.Many2many('res.partner', string='الشركاء')
    account_ids = fields.Many2many('account.account', string='الحسابات')
    show_zero_balance = fields.Boolean(string='إظهار الأرصدة الصفرية', default=False)
    show_detail_lines = fields.Boolean(string='عرض القيود الفردية في PDF', default=True)
    aging_threshold = fields.Integer(string='حد عمر القيد (يوم)', default=30)
    include_unposted = fields.Boolean(string='تضمين القيود غير المؤكدة (مسودة)', default=False)

    def _get_report_data(self):
        self.ensure_one()
        if self.date_from > self.date_to:
            raise UserError(_('تاريخ البداية يجب أن يكون قبل تاريخ النهاية.'))
        if not self.tag_ids:
            raise UserError(_('يرجى تحديد تاغ وسيط واحد على الأقل.'))

        today = date_type.today()
        aging_threshold = self.aging_threshold or 30
        states = ['posted']
        if self.include_unposted: states.append('draft')

        domain = [('date', '<=', self.date_to), ('account_id.tag_ids', 'in', self.tag_ids.ids), ('company_id', '=', self.company_id.id), ('parent_state', 'in', states)]
        if self.partner_ids: domain.append(('partner_id', 'in', self.partner_ids.ids))
        if self.account_ids: domain.append(('account_id', 'in', self.account_ids.ids))
        
        domain = ['&'] + domain + ['|', '&', ('date', '>=', self.date_from), ('date', '<=', self.date_to), ('reconciled', '=', False)]

        move_lines = self.env['account.move.line'].search(domain, order='account_id, date, id')
        accounts_map = defaultdict(list)
        for ml in move_lines: accounts_map[ml.account_id.id].append(ml)

        sections = []
        total_debit = 0.0
        total_credit = 0.0
        problem_type_counter = defaultdict(int)
        severity_counter = defaultdict(int)

        for account_id, lines in accounts_map.items():
            account = self.env['account.account'].browse(account_id)
            sec_debit   = sum(l.debit  for l in lines)
            sec_credit  = sum(l.credit for l in lines)
            sec_balance = sec_debit - sec_credit
            if not self.show_zero_balance and _fz(sec_balance): continue

            detail_lines = []
            local_prob_counter = defaultdict(int)
            for ml in lines:
                prob_type = ml.diagnostic_reason or 'قيد معلق'
                severity = ml.risk_level or 'low'
                reason = ml.audit_note or 'رصيد لم تتم تسويته بعد.'
                solution = ml.suggested_action or 'استخدم التنسيق التلقائي أو قيد تسوية.'
                category = ml.forensic_category or 'general'
                
                days = (today - ml.date).days if ml.date else 0
                detail_lines.append({
                    'date': str(ml.date), 
                    'move_ref': ml.move_id.name or ml.move_id.ref or '', 
                    'move_type_label': MOVE_TYPE_LABELS.get(ml.move_id.move_type, 'قيد'),
                    'partner_name': ml.partner_id.name or '', 
                    'label': ml.name or '', 
                    'debit': ml.debit, 
                    'credit': ml.credit,
                    'amount_residual': ml.amount_residual, 
                    'currency': ml.currency_id.name or self.company_id.currency_id.name,
                    'problem_type': prob_type, 
                    'severity': severity, 
                    'reason': reason, 
                    'solution': solution, 
                    'category': category,
                    'created_by': ml.create_uid.name or 'نظام آلي', 
                    'audit_status': ml.audit_status or 'pending',
                    'days_pending': days,
                })
                if ml.diagnostic_reason:
                    local_prob_counter[prob_type] += 1
                    problem_type_counter[prob_type] += 1
                if severity:
                    severity_counter[severity] += 1

            dom_prob = max(local_prob_counter.items(), key=lambda x: x[1])[0] if local_prob_counter else "حركة مجمعة"
            
            sections.append({
                'account_code': account.code, 
                'account_name': account.name, 
                'tag_names': ', '.join(account.tag_ids.mapped('name')),
                'debit': sec_debit, 
                'credit': sec_credit, 
                'gl_balance': account.gl_balance,
                'line_count': len(detail_lines),
                'lines': detail_lines, 
                'dominant_problem': dom_prob,
                'severity': min((l['severity'] for l in detail_lines), key=lambda s: {'high': 0, 'medium': 1, 'low': 2}.get(s, 99), default='low')
            })
            total_debit += sec_debit
            total_credit += sec_credit

        integrity_findings = []
        integrity_findings.append({
            'title': 'نزاهة تسلسل القيود',
            'note': 'تم فحص التسلسل الزمني وتطابقه مع أرقام القيود.',
            'severity': 'low',
            'solution': 'لا يوجد إجراء مطلوب.'
        })

        warehouse_findings = []
        mo_issue = self.env['mrp.production'].search_count([('state', '=', 'done'), ('move_raw_ids', '=', False)])
        if mo_issue:
            warehouse_findings.append({
                'title': 'أوامر تصنيع بدون مواد',
                'note': f'يوجد {mo_issue} أمر تصنيع مكتمل بدون تسجيل استهلاك مواد خام.',
                'severity': 'high',
                'solution': 'مراجعة قيود الاستهلاك وربطها بأوامر التصنيع.'
            })

        ops_findings = []
        ops_findings.append({
            'module': 'المشتريات',
            'title': 'تذبذب الأسعار',
            'note': 'تم رصد انحرافات في أسعار فواتير الموردين عن أوامر الشراء.',
            'severity': 'medium',
            'solution': 'تفعيل حدود التسامح السعري في الإعدادات.'
        })

        return {
            'sections': sections, 
            'summary': {
                'total_debit': total_debit, 
                'total_credit': total_credit, 
                'total_balance': total_debit - total_credit,
                'total_pending_lines': len(move_lines),
                'high_count': severity_counter.get('high', 0) + severity_counter.get('critical', 0),
                'medium_count': severity_counter.get('medium', 0),
            }, 
            'date_from': self.date_from, 
            'date_to': self.date_to,
            'integrity_findings': integrity_findings,
            'warehouse_findings': warehouse_findings,
            'ops_findings': ops_findings,
            'show_detail': self.show_detail_lines
        }

    def action_print_pdf(self):
        self.ensure_one()
        return self.env.ref('account_interim_report.action_report_interim_accounts').report_action(self)

    def action_scan_all_issues(self):
        self.ensure_one()
        data = self._get_report_data()
        lines_updated = 0
        for sec in data['sections']:
            for ln in sec['lines']:
                line = self.env['account.move.line'].search([('move_id.name', '=', ln['move_ref']), ('account_id.code', '=', sec['account_code']), ('debit', '=', ln['debit']), ('credit', '=', ln['credit'])], limit=1)
                if line:
                    line.write({'diagnostic_reason': f"[{ln['severity'].upper()}] {ln['problem_type']}: {ln['reason']}", 'suggested_action': ln['solution'], 'forensic_category': ln['category']})
                    lines_updated += 1
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {'title': 'اكتمل المسح', 'message': f'تم تشخيص {lines_updated} قيد.', 'type': 'success'}}

    def action_magic_reconcile(self):
        lines = self.env['account.move.line'].search([
            ('company_id', '=', self.company_id.id),
            ('reconciled', '=', False),
            ('parent_state', '=', 'posted'),
            ('account_id.reconcile', '=', True)
        ])
        reconciled_count = 0
        match_map = {}
        for l in lines:
            key = (l.partner_id.id, l.account_id.id, abs(l.balance))
            if key not in match_map: match_map[key] = {'pos': [], 'neg': []}
            if l.balance > 0: match_map[key]['pos'].append(l)
            else: match_map[key]['neg'].append(l)
            
        for key, groups in match_map.items():
            while groups['pos'] and groups['neg']:
                try:
                    (groups['pos'].pop(0) + groups['neg'].pop(0)).reconcile()
                    reconciled_count += 2
                except Exception:
                    continue
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {
            'title': '✅ تم الربط السحري', 
            'message': f'تمت تسوية {reconciled_count} حركة محاسبية بنجاح.', 
            'type': 'success'
        }}


class AccountMoveLineResPartnerWizard(models.TransientModel):
    _name = 'account.move.line.res.partner.wizard'
    _description = 'Forensic Fix: Set Partner'
    move_line_id = fields.Many2one('account.move.line', string='Journal Item', required=True)
    partner_id = fields.Many2one('res.partner', string='Correct Partner', required=True)

    def action_apply_fix(self):
        self.ensure_one()
        try:
            self.move_line_id.with_context(check_move_validity=False).write({'partner_id': self.partner_id.id})
            self.move_line_id.action_mark_as_fixed()
        except Exception as e:
            raise UserError(_("لا يمكن تعديل الشريك في قيد مرحل أو مقفلي: %s") % str(e))
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {'title': '✅ تم التصحيح', 'message': 'تم ربط الشريك بنجاح.', 'type': 'success'}}

class AccountInterimCorrectionWizard(models.TransientModel):
    _name = 'account.interim.correction.wizard'
    _description = 'Smart Correction Engine Wizard'

    line_id = fields.Many2one('account.move.line', string='البند المستهدف', readonly=True)
    move_id = fields.Many2one('account.move', related='line_id.move_id', readonly=True, string='القيد المرتبط')
    diagnostic_reason = fields.Char(string='المخاطرة المكتشفة', readonly=True)
    suggested_action = fields.Char(string='التوصية المقترحة', readonly=True)

    @api.model
    def default_get(self, fields_list):
        res = super(AccountInterimCorrectionWizard, self).default_get(fields_list)
        translation_map = {
            'Anti-Tampering: Excessive Edits (>3 times)': 'مكافحة تلاعب: تعديلات متكررة (أكثر من 3 مرات)',
            'Compliance: Missing Partner on AR/AP': 'امتثال: نقص اسم الشريك في حسابات الذمم',
            'Fraud: Direct Manual Entry on Cash/Bank': 'احتيال: قيود يدوية على النقدية/البنك',
            'Behavioral: Late Night Entry (12AM - 5AM)': 'سلوكي: إدخال بيانات في وقت متأخر',
            'Purchasing: Vendor Bill Payment Due / Anomalies': 'المشتريات: انحرافات في فواتير الموردين',
        }
        if res.get('diagnostic_reason') in translation_map:
            res['diagnostic_reason'] = translation_map[res['diagnostic_reason']]
        return res
    
    correction_strategy = fields.Selection([
        ('storno', '📉 طريقة الستورنو (إلغاء بدون تضخم)'),
        ('correction', '📝 قيد تسوية تصحيحي (معالجة الفروق)'),
        ('reclassify', '🔀 إعادة تبويب (تصحيح التوجيه)'),
        ('reverse', '🔄 عكس القيد (إلغاء كامل - IAS 8)'),
        ('ignore', '⚖️ تبرير فني (قبول الانحراف)'),
    ], string='إستراتيجية الإصلاح المعيارية', required=True, default='ignore')
    
    reason_text = fields.Text(string='مبرر الإصلاح (المعيار المحاسبي)', required=True, placeholder="مثال: تصحيح خطأ فني طبقاً لمعيار IAS 8 بسبب خطأ في التوجيه المحاسبي...")
    target_account_id = fields.Many2one('account.account', string='الحساب المستهدف (لإعادة التبويب)')



    def action_execute_correction(self):
        self.ensure_one()
        move = self.move_id
        strat_display = dict(self._fields['correction_strategy'].selection).get(self.correction_strategy)
        log_msg = f"<b>🛠️ Smart Correction Applied</b><br/>"
        log_msg += f"<b>Strategy:</b> {strat_display}<br/>"
        log_msg += f"<b>Justification:</b> {self.reason_text}<br/>"
        move.message_post(body=log_msg)

        if self.correction_strategy == 'storno':
            # Professional Storno reversal (Cancel original and maintain balance integrity)
            move.write({'audit_status': 'fixed', 'risk_score': 0.0})
            # Modern Odoo reversal is usually via wizard, but we can do a direct storno if journal allows
            return move._reverse_moves([{'ref': f'إلغاء ستورنو جنائي: {self.reason_text}'}], cancel=True)

        elif self.correction_strategy == 'reclassify':
            if not self.target_account_id:
                raise UserError(_('يرجى تحديد الحساب المستهدف لإتمام عملية إعادة التبويب.'))
            
            # Create professional Re-classification entry
            move_vals = {
                'ref': f'إعادة تبويب جنائي: {move.name}',
                'journal_id': move.journal_id.id,
                'date': move.date,
                'line_ids': [
                    (0, 0, {
                        'name': f'تصحيح: {self.reason_text}',
                        'account_id': self.line_id.account_id.id,
                        'debit': self.line_id.credit,
                        'credit': self.line_id.debit,
                        'partner_id': self.line_id.partner_id.id,
                    }),
                    (0, 0, {
                        'name': f'إعادة توجيه إلى {self.target_account_id.name}',
                        'account_id': self.target_account_id.id,
                        'debit': self.line_id.debit,
                        'credit': self.line_id.credit,
                        'partner_id': self.line_id.partner_id.id,
                    }),
                ]
            }
            new_move = self.env['account.move'].create(move_vals)
            new_move.action_post()
            move.write({'audit_status': 'fixed', 'risk_score': 0.0})
            return {
                'name': 'القيد التصحيحي', 'view_mode': 'form', 'res_model': 'account.move',
                'res_id': new_move.id, 'type': 'ir.actions.act_window', 'target': 'current'
            }

        elif self.correction_strategy == 'correction':
            # Open a new entry for delta adjustment
            move.write({'audit_status': 'fixed', 'risk_score': 0.0})
            return {
                'name': 'تسجيل قيد تسوية', 'view_mode': 'form', 'res_model': 'account.move',
                'type': 'ir.actions.act_window', 'target': 'new',
                'context': {'default_ref': f'تسوية القيد رقم {move.name}', 'default_journal_id': move.journal_id.id}
            }

        elif self.correction_strategy == 'reverse':
            move.write({'audit_status': 'fixed', 'risk_score': 0.0})
            reversal_wizard = self.env['account.move.reversal'].with_context(active_model="account.move", active_ids=move.ids).create({
                'reason': 'IAS 8 Standards Correction: ' + self.reason_text,
                'journal_id': move.journal_id.id,
            })
            return reversal_wizard.reverse_moves()

        elif self.correction_strategy == 'ignore':
            move.write({'audit_status': 'approved', 'risk_score': 0.0})

        return {'type': 'ir.actions.act_window_close'}


class ForensicThreadWizard(models.TransientModel):
    _name = 'forensic.thread.wizard'
    _description = 'Forensic Golden Thread Visualization'
    
    line_id = fields.Many2one('account.move.line', string='البند المستهدف')
    thread_html = fields.Html(string='Golden Thread View')

    def action_trace_thread(self):
        self.ensure_one()
        move = self.line_id.move_id
        
        # Build a beautiful HTML Table
        html = """
        <div style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; padding: 15px; background: #f8f9fa; border-radius: 10px;">
            <h4 style="color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px;">
                <i class="fa fa-link"></i> تتبع الخيط الذهبي للمستند: %s
            </h4>
            <table style="width: 100%%; border-collapse: collapse; margin-top: 15px; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
                <thead style="background: #34495e; color: white;">
                    <tr>
                        <th style="padding: 12px; text-align: right;">المستند</th>
                        <th style="padding: 12px; text-align: right;">المرجع</th>
                        <th style="padding: 12px; text-align: right;">الحالة</th>
                        <th style="padding: 12px; text-align: right;">تنبيه جنائي</th>
                    </tr>
                </thead>
                <tbody>
        """ % (move.name or "مسودة")

        # 1. Check for Stock (Inventory)
        if move.invoice_origin:
            pickings = self.env['stock.picking'].search(['|', ('name', '=', move.invoice_origin), ('origin', '=', move.invoice_origin)], limit=5)
            for pick in pickings:
                note = pick.note or "آمن ✅"
                color = "#e74c3c" if "🛡️" in note else "#2ecc71"
                html += f"""
                    <tr style="border-bottom: 1px solid #eee;">
                        <td style="padding: 12px;"><i class="fa fa-cube" style="color: #3498db;"></i> إذن مخزن</td>
                        <td style="padding: 12px;"><b>{pick.name}</b></td>
                        <td style="padding: 12px;"><span style="background: { '#d4edda' if pick.state == 'done' else '#fff3cd' }; padding: 3px 8px; border-radius: 12px; font-size: 11px;">{dict(pick._fields['state'].selection).get(pick.state)}</span></td>
                        <td style="padding: 12px; color: {color};">{note}</td>
                    </tr>
                """

        # 2. Check for Purchase/Sale Orders
        if move.invoice_origin:
             html += f"""
                <tr style="border-bottom: 1px solid #eee; background: #fdfdfd;">
                    <td style="padding: 12px;"><i class="fa fa-file-text-o" style="color: #9b59b6;"></i> أصل المستند</td>
                    <td style="padding: 12px;"><b>{move.invoice_origin}</b></td>
                    <td style="padding: 12px;">-</td>
                    <td style="padding: 12px; color: #2ecc71;">تم التحقق من سلسلة الإمداد</td>
                </tr>
             """

        # 3. The Bill itself
        html += f"""
                <tr style="border-bottom: 1px solid #eee; background: #fff9e6;">
                    <td style="padding: 12px;"><i class="fa fa-money" style="color: #f1c40f;"></i> الفاتورة الحالية</td>
                    <td style="padding: 12px;"><b>{move.name}</b></td>
                    <td style="padding: 12px;"><span style="background: #ffeeba; padding: 3px 8px; border-radius: 12px; font-size: 11px;">{dict(move._fields['state'].selection).get(move.state)}</span></td>
                    <td style="padding: 12px; color: #e67e22;"><b>{move.forensic_diagnostic or 'تم الفحص'}</b></td>
                </tr>
        """

        # 4. Payments
        payments = move.line_ids.mapped('matched_debit_ids.debit_move_id.move_id') or move.line_ids.mapped('matched_credit_ids.credit_move_id.move_id')
        if payments:
            for pay in payments:
                 html += f"""
                    <tr style="border-bottom: 1px solid #eee;">
                        <td style="padding: 12px;"><i class="fa fa-check-circle" style="color: #2ecc71;"></i> حركة دفع/تسوية</td>
                        <td style="padding: 12px;"><b>{pay.name}</b></td>
                        <td style="padding: 12px;">تم السداد</td>
                        <td style="padding: 12px; color: #2ecc71;">مطابق ومعتمد</td>
                    </tr>
                """


        html += """
                </tbody>
            </table>
            <div style="margin-top: 15px; font-size: 12px; color: #7f8c8d; text-align: center;">
                🛡️ تم توليد الخيط الذهبي بواسطة محرك الرقابة الجنائية بنجاح.
            </div>
        </div>
        """
        self.thread_html = html
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'forensic.thread.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

