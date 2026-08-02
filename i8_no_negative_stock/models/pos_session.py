# -*- coding: utf-8 -*-
import logging, re
from odoo import api, models, _, fields

_logger = logging.getLogger(__name__)
EMAIL_RE = re.compile(r"[^@,\s]+@[^@,\s]+\.[^@,\s]+")

class PosSession(models.Model):
    _inherit = "pos.session"

    def _i8_parse_recipients(self, recipients_str):
        if not recipients_str:
            return []
        emails = []
        for raw in recipients_str.split(","):
            e = (raw or "").strip()
            if e and EMAIL_RE.match(e):
                emails.append(e)
        return emails

    def _i8_default_email_from(self, company):
        ICP = self.env['ir.config_parameter'].sudo()
        # 1) company email
        if company.email:
            return company.email
        # 2) global default
        default_from = ICP.get_param('mail.default.from')
        if default_from:
            return default_from
        # 3) catchall@domain
        domain = ICP.get_param('mail.catchall.domain')
        alias = ICP.get_param('mail.catchall.alias') or 'notifications'
        if domain:
            return f"{alias}@{domain}"
        # 4) last resort: company partner email or empty
        return company.partner_id.email or False

    def _i8_send_low_stock_email(self, config, loc, prod, remaining, threshold):
        recipients = self._i8_parse_recipients(config.low_stock_email_recipients)
        if not recipients:
            return
        subject = _("POS Low Stock: %(p)s at %(l)s (≤ %(t)s)") % {
            "p": prod.display_name, "l": loc.display_name, "t": threshold
        }
        body = _(
            "<p><b>Low-stock alert</b></p>"
            "<p>Product: <b>%(p)s</b><br/>Location: <b>%(l)s</b><br/>POS: %(pos)s<br/>"
            "Threshold: %(t)s<br/>Remaining (after current order): <b>%(r).2f</b></p>"
        ) % {
            "p": prod.display_name, "l": loc.display_name,
            "pos": config.display_name, "t": threshold, "r": remaining
        }

        email_from = self._i8_default_email_from(config.company_id)
        Mail = self.env['mail.mail'].sudo()
        Mail.create({
            "subject": subject,
            "body_html": body,
            "email_to": ",".join(recipients),
            "email_from": email_from,             # <-- force default sender
            "author_id": config.company_id.partner_id.id,  # optional: show company as author
        }).send()
        _logger.info("[i8_low_stock_email] sent from %s → %s | %s | remaining=%.2f (thr=%s)",
                     email_from, recipients, prod.display_name, remaining, threshold)

    @api.model
    def i8_check_low_stock(self, session_id, needs_map):
        """
        Returns list for UI; ALSO sends one-time emails if recipients set.
        Email: once on crossing (remaining <= threshold). Resets when remaining > threshold.
        """
        session = self.browse(session_id).sudo()
        if not session.exists():
            _logger.info("[i8_low_stock] no session %s", session_id)
            return []

        config = session.config_id
        enabled = bool(getattr(config, "low_stock_alert_enabled", False))
        threshold = int(getattr(config, "low_stock_threshold", 0) or 0)
        loc_id = (
            config.picking_type_id.warehouse_id.lot_stock_id.id
            if (config.picking_type_id and config.picking_type_id.warehouse_id and config.picking_type_id.warehouse_id.lot_stock_id)
            else (config.stock_location_id.id if config.stock_location_id else False)
        )
        if not enabled or not loc_id or not needs_map:
            return []

        loc = self.env["stock.location"].browse(loc_id)
        ProductCtx = self.env["product.product"] \
            .with_company(config.company_id) \
            .with_context(location=loc_id)
        Flag = self.env["i8.low.stock.flag"].sudo()

        results = []
        recipients_present = bool(self._i8_parse_recipients(config.low_stock_email_recipients))

        for pid, need in (needs_map or {}).items():
            prod = ProductCtx.browse(int(pid)).exists()
            if not prod:
                continue
            available = getattr(prod, "free_qty", prod.qty_available)
            need = float(needs_map.get(pid) or 0.0)
            remaining = float(available) - need
            hit = remaining <= threshold
            results.append({
                "product_id": prod.id,
                "display_name": prod.display_name,
                "available": float(available),
                "remaining": remaining,
                "threshold_hit": hit,
            })

            # Email only if recipients configured
            if not recipients_present:
                continue

            flag = Flag.search([
                ("company_id", "=", config.company_id.id),
                ("config_id", "=", config.id),
                ("product_id", "=", prod.id),
                ("location_id", "=", loc_id),
            ], limit=1)

            if flag and available > threshold:
                flag.unlink()
                flag = False

            if (not flag) and hit:
                Flag.create({
                    "company_id": config.company_id.id,
                    "config_id": config.id,
                    "product_id": prod.id,
                    "location_id": loc_id,
                    "last_remaining": remaining,
                    "notified_at": fields.Datetime.now(),
                })
                self._i8_send_low_stock_email(config, loc, prod, remaining, threshold)

        return results
