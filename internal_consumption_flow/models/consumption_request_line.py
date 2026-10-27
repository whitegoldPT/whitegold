# -*- coding: utf-8 -*-
from odoo import api, fields, models, _

class ConsumptionRequestLine(models.Model):
    _name = "consumption.request.line"
    _inherit = 'analytic.mixin'
    _description = "Consumption Request Line"

    request_id = fields.Many2one("consumption.request", string="Request", ondelete="cascade")
    product_id = fields.Many2one("product.product", string="Product", required=True)
    description = fields.Char(string="Description", related="product_id.display_name", readonly=False)
    product_qty = fields.Float(string="Quantity", default=1.0, required=True)
    product_uom_id = fields.Many2one("uom.uom", string="Unit of Measure", related="product_id.uom_id")
    employee_id = fields.Many2one("hr.employee", related="request_id.employee_id", store=True)
    
    # Stock Output / Expense Account - Primary: Stock Output Account (حساب خروج البضاعة)
    account_id = fields.Many2one(
        "account.account", 
        string="حساب خروج البضاعة (Stock Output)",
        compute="_compute_account_id",
        store=True,
        readonly=False,
        precompute=True,
        required=False,
    )
    # Field analytic_distribution is inherited from analytic.mixin

    @api.depends('employee_id', 'request_id.department_id')
    def _compute_analytic_distribution(self):
        plan = self.env.ref('internal_consumption_flow.analytic_plan_general_expenses', raise_if_not_found=False)
        for line in self:
            department = line.request_id.department_id
            if not department or not plan:
                line.analytic_distribution = False
                continue
            
            # Find or Create Analytic Account for this Department
            analytic_account = self.env['account.analytic.account'].search([
                ('name', '=', department.name),
                ('plan_id', '=', plan.id)
            ], limit=1)
            
            if not analytic_account:
                analytic_account = self.env['account.analytic.account'].create({
                    'name': department.name,
                    'plan_id': plan.id
                })
            
            # Odoo 18 Analytic Distribution format: { 'account_id': percentage }
            line.analytic_distribution = {str(analytic_account.id): 100.0}

    @api.depends("product_id")
    def _compute_account_id(self):
        for line in self:
            if not line.product_id:
                line.account_id = False
                continue
            
            account = False
            
            # 1. Primary: Stock Output Account from Category or its parents (حساب خروج البضاعة على فئة الصنف)
            categ = line.product_id.categ_id
            while categ and not account:
                account = getattr(categ, 'property_stock_account_output_categ_id', False)
                categ = categ.parent_id

            # 2. Stock Output Account via standard get_product_accounts()
            if not account and hasattr(line.product_id, 'product_tmpl_id'):
                try:
                    accounts = line.product_id.product_tmpl_id.get_product_accounts()
                    account = accounts.get('stock_output')
                except Exception:
                    pass

            # 3. Fallback: Expense Account from Product Card (حساب المصروف على كارت الصنف)
            if not account:
                account = getattr(line.product_id, 'property_account_expense_id', False)
            
            # 4. Fallback: Expense Account from Category or its parents (حساب المصروف على فئة الصنف)
            if not account:
                categ = line.product_id.categ_id
                while categ and not account:
                    account = getattr(categ, 'property_account_expense_categ_id', False)
                    categ = categ.parent_id

            # 5. Fallback: Expense Account via standard get_product_accounts()
            if not account and hasattr(line.product_id, 'product_tmpl_id'):
                try:
                    accounts = line.product_id.product_tmpl_id.get_product_accounts()
                    account = accounts.get('expense')
                except Exception:
                    pass

            # 6. Fallback across companies: If branch company has no account, fallback to Main Company
            if not account:
                main_company = self.env['res.company'].search([], order='id asc', limit=1)
                if main_company and main_company != self.env.company:
                    categ = line.product_id.categ_id
                    while categ and not account:
                        account = getattr(categ.with_company(main_company), 'property_stock_account_output_categ_id', False)
                        categ = categ.parent_id
                    if not account:
                        account = getattr(line.product_id.with_company(main_company), 'property_account_expense_id', False)
                    if not account:
                        categ = line.product_id.categ_id
                        while categ and not account:
                            account = getattr(categ.with_company(main_company), 'property_account_expense_categ_id', False)
                            categ = categ.parent_id

            line.account_id = account or False
