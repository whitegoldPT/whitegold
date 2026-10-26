from odoo import fields, models


class ConsumptionApprovalCategory(models.Model):
    _name = "consumption.approval.category"
    _description = "Consumption Approval Category"
    _order = "sequence, id"

    name = fields.Char(required=True, string="Category Name")
    sequence = fields.Integer(default=10)
    approver_ids = fields.Many2many(
        "res.users",
        "consumption_approval_category_user_rel",
        "category_id",
        "user_id",
        string="Required Approvers",
        help="Users who must approve requests in this category.",
    )
    active = fields.Boolean(default=True)
    description = fields.Text()


class ConsumptionApprovalLine(models.Model):
    """Tracks individual approval decisions on a request."""
    _name = "consumption.approval.line"
    _description = "Consumption Approval Line"
    _order = "sequence, id"

    request_id = fields.Many2one(
        "consumption.request", required=True, ondelete="cascade",
    )
    category_id = fields.Many2one(
        "consumption.approval.category", required=True, string="Approval Category",
    )
    approver_id = fields.Many2one(
        "res.users", string="Approver", required=True,
    )
    sequence = fields.Integer(related="category_id.sequence", store=True)
    status = fields.Selection(
        [("pending", "Pending"), ("approved", "Approved"), ("refused", "Refused")],
        default="pending",
        required=True,
    )
    approval_date = fields.Datetime(string="Decision Date")
    note = fields.Text(string="Comment")
