# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class PartialReceiveReasonWizard(models.TransientModel):
    _name = 'partial.receive.reason.wizard'
    _description = 'Partial Receive Reason Wizard'

    reason = fields.Text(
        string='Reason for Partial Receive',
        required=True,
        help="Please specify why you are not receiving all products"
    )
    transfer_id = fields.Many2one('stock.internal.transfer', string="Transfer")
    deleted_lines_info = fields.Text(
        string='Products Not Received',
        readonly=True,
        help="List of products that were not received"
    )

    @api.model
    def default_get(self, fields):
        """Load default values including deleted lines info"""
        res = super(PartialReceiveReasonWizard, self).default_get(fields)
        context = self._context

        if 'deleted_lines_info' in context:
            deleted_lines = context.get('deleted_lines_info', [])
            if deleted_lines:
                res['deleted_lines_info'] = _("The following products were not received:\n") + "\n".join(deleted_lines)

        return res

    def action_confirm(self):
        for wizard in self:
            if wizard.transfer_id:
                # Update transfer with reason
                wizard.transfer_id.write({
                    'partial_receive_reason': wizard.reason
                })

                # Post message to chatter with all details
                message = _("Partial receive reason: %s") % wizard.reason
                if wizard.deleted_lines_info:
                    message += "\n\n" + wizard.deleted_lines_info

                wizard.transfer_id.message_post(body=message)

        return {'type': 'ir.actions.act_window_close'}