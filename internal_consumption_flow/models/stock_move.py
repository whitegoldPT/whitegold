from odoo import api, fields, models

class StockMove(models.Model):
    _inherit = "stock.move"

    consumption_line_id = fields.Many2one("consumption.request.line", string="Consumption Line", readonly=True)
    analytic_distribution = fields.Json(string="Analytic Distribution", readonly=False, store=True)
    analytic_precision = fields.Integer(string="Analytic Precision", default=2)

    def _get_dest_account(self, accounts_data):
        """Override to use the manual account from the consumption request if applicable"""
        if self.consumption_line_id and self.consumption_line_id.account_id:
            return self.consumption_line_id.account_id.id
        return super()._get_dest_account(accounts_data)

    def _prepare_account_move_line(self, qty, cost, credit_account_id, debit_account_id, svl_id, description):
        """
        Force the debit account and analytic distribution to be the ones selected on the 
        Consumption Request Line if this move is a consumption receipt move.
        """
        res = super()._prepare_account_move_line(qty, cost, credit_account_id, debit_account_id, svl_id, description)
        
        # If we have a consumption line, we want to ensure the DEBIT (expense) side uses our account
        if self.consumption_line_id and self.consumption_line_id.account_id:
            for line in res:
                # Identification logic: the debit line matches the debit_account_id passed by stock_account
                if line[2].get('account_id') == debit_account_id:
                    line[2]['account_id'] = self.consumption_line_id.account_id.id
                    if self.analytic_distribution:
                        line[2]['analytic_distribution'] = self.analytic_distribution
        
        return res
