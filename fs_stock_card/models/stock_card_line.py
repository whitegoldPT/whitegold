from odoo import _, api, fields, models


class StockCardLine(models.TransientModel):
    _name = 'stock.card.line'
    _description = 'Stock Card Line'
    _order = 'product_id, sequence, date, id'

    wizard_id = fields.Many2one('stock.card.wizard', string='Wizard', ondelete='cascade')
    company_id = fields.Many2one('res.company', related='wizard_id.company_id', store=True)
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id')
    sequence = fields.Integer(string='Sequence', default=10)
    line_type = fields.Selection([
        ('opening', 'Opening Balance'),
        ('transaction', 'Transaction'),
        ('closing', 'Closing Balance'),
    ], string='Line Type', default='transaction')

    date = fields.Date(string='Date')
    product_id = fields.Many2one('product.product', string='Product')
    categ_id = fields.Many2one('product.category', string='Category', related='product_id.categ_id', store=True)
    uom_id = fields.Many2one('uom.uom', string='Unit', related='product_id.uom_id')

    reference = fields.Char(string='Reference')
    source_document = fields.Char(string='Source Document')
    partner_id = fields.Many2one('res.partner', string='Partner')

    qty_in = fields.Float(string='In Qty', digits='Product Unit of Measure')
    qty_out = fields.Float(string='Out Qty', digits='Product Unit of Measure')
    balance = fields.Float(string='Balance', digits='Product Unit of Measure', aggregator=None)
    initial_balance = fields.Float(string='Initial Balance', digits='Product Unit of Measure', aggregator=None)

    unit_cost = fields.Monetary(string='Unit Cost', aggregator=None)
    value_in = fields.Monetary(string='Value In')
    value_out = fields.Monetary(string='Value Out')
    balance_value = fields.Monetary(string='Balance Value', aggregator=None)

    location_id = fields.Many2one('stock.location', string='Source Location')
    location_dest_id = fields.Many2one('stock.location', string='Destination Location')
    move_id = fields.Many2one('stock.move', string='Stock Move')
    move_line_id = fields.Many2one('stock.move.line', string='Stock Move Line')

    @api.depends('line_type', 'reference')
    def _compute_display_name(self):
        for line in self:
            if line.line_type == 'opening':
                line.display_name = _('Opening Balance')
            elif line.line_type == 'closing':
                line.display_name = _('Closing Balance')
            else:
                line.display_name = line.reference or ''
