import base64
import io
from datetime import datetime, time, timedelta

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare

try:
    import xlsxwriter
except ImportError:
    xlsxwriter = None


class StockCardWizard(models.TransientModel):
    _name = 'stock.card.wizard'
    _description = 'Stock Card Report Wizard'
    _check_company_auto = True

    date_from = fields.Date(
        string='Start Date',
        required=True,
        default=lambda self: fields.Date.context_today(self).replace(day=1)
    )
    date_to = fields.Date(
        string='End Date',
        required=True,
        default=fields.Date.context_today
    )

    location_id = fields.Many2one(
        'stock.location',
        string='Location',
        domain="[('usage', 'in', ['internal', 'transit'])]",
        required=True,
        check_company=True,
    )
    include_child_locations = fields.Boolean(
        string='Include Child Locations',
        default=True
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company
    )

    filter_by = fields.Selection([
        ('product', 'Product'),
        ('category', 'Product Category'),
    ], string='Filter By', default='product', required=True)

    include_zero_movements = fields.Boolean(
        string='Include Zero Movements',
        default=False
    )

    group_by = fields.Selection([
        ('product', 'Product'),
        ('category', 'Category'),
    ], string='Group By', default='product', required=True)

    product_ids = fields.Many2many(
        'product.product',
        'stock_card_wizard_product_rel',
        'wizard_id',
        'product_id',
        string='Products',
        domain="[('is_storable', '=', True)]",
        check_company=True,
    )
    categ_ids = fields.Many2many(
        'product.category',
        'stock_card_wizard_category_rel',
        'wizard_id',
        'categ_id',
        string='Product Categories'
    )

    line_ids = fields.One2many('stock.card.line', 'wizard_id', string='Stock Card Lines')
    excel_file = fields.Binary(string='Excel File', attachment=False, readonly=True)
    excel_filename = fields.Char(string='Excel Filename', readonly=True)

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for wizard in self:
            if wizard.date_from > wizard.date_to:
                raise ValidationError(_('The start date must be before or equal to the end date.'))

    @api.onchange('company_id')
    def _onchange_company_id(self):
        if self.location_id.company_id and self.location_id.company_id != self.company_id:
            self.location_id = False

    @api.onchange('filter_by')
    def _onchange_filter_by(self):
        if self.filter_by == 'product':
            self.categ_ids = False
        else:
            self.product_ids = False

    def _get_locations(self):
        """Get all locations including children if specified"""
        self.ensure_one()
        if self.include_child_locations:
            return self.env['stock.location'].search([
                ('id', 'child_of', self.location_id.id),
                ('usage', 'in', ['internal', 'transit'])
            ])
        return self.location_id

    def _get_products(self):
        """Get products based on filter criteria"""
        self.ensure_one()
        domain = [
            ('is_storable', '=', True),
            ('company_id', 'in', [self.company_id.id, False]),
        ]

        if self.filter_by == 'product' and self.product_ids:
            domain.append(('id', 'in', self.product_ids.ids))
        elif self.filter_by == 'category' and self.categ_ids:
            domain.append(('categ_id', 'child_of', self.categ_ids.ids))

        # Archived products may still have stock or movements in the period
        return self.env['product.product'].with_context(active_test=False).search(domain, order='name')

    def _get_datetime_range(self):
        """Return the UTC naive datetimes [start, end) covering the period in the user's timezone"""
        self.ensure_one()
        tz = pytz.timezone(self.env.context.get('tz') or self.env.user.tz or 'UTC')

        def to_utc(day):
            return tz.localize(datetime.combine(day, time.min)).astimezone(pytz.utc).replace(tzinfo=None)

        return to_utc(self.date_from), to_utc(self.date_to + timedelta(days=1))

    def _get_opening_balances(self, products, locations, date_start):
        """Return {product_id: quantity} at the given location before date_start, in product UoM"""
        self.ensure_one()
        MoveLine = self.env['stock.move.line']
        base_domain = [
            ('state', '=', 'done'),
            ('company_id', '=', self.company_id.id),
            ('product_id', 'in', products.ids),
            ('date', '<', date_start),
        ]
        incoming = MoveLine._read_group(
            base_domain + [('location_dest_id', 'in', locations.ids), ('location_id', 'not in', locations.ids)],
            ['product_id'], ['quantity_product_uom:sum'],
        )
        outgoing = MoveLine._read_group(
            base_domain + [('location_id', 'in', locations.ids), ('location_dest_id', 'not in', locations.ids)],
            ['product_id'], ['quantity_product_uom:sum'],
        )
        balances = dict.fromkeys(products.ids, 0.0)
        for product, qty in incoming:
            balances[product.id] += qty
        for product, qty in outgoing:
            balances[product.id] -= qty
        return balances

    def _get_transactions(self, products, locations, date_start, date_end):
        """Return the done move lines of the period entering or leaving the locations"""
        self.ensure_one()
        return self.env['stock.move.line'].search([
            ('state', '=', 'done'),
            ('company_id', '=', self.company_id.id),
            ('product_id', 'in', products.ids),
            ('date', '>=', date_start),
            ('date', '<', date_end),
            '|',
            ('location_id', 'in', locations.ids),
            ('location_dest_id', 'in', locations.ids),
        ], order='date, id')

    # Stock valuation layers are only readable by inventory managers (stock_account ACL). The stock
    # card is a valuation report: any user allowed to run it sees the unit costs of the products
    # it lists. Reads are limited to the wizard company and to the layers dated before the end of
    # the period, so that later corrections never change a past period.

    def _get_unit_costs_at(self, products, operator, at_datetime):
        """Return {product_id: average unit cost} of the company valuation at the UTC datetime

        Layers count when their create_date compares with operator ('<' or '<=') to at_datetime.
        When the company had no stock, fall back on the last layer unit cost, then on the current
        cost: Odoo creates no revaluation layer for a cost change made without stock.
        """
        self.ensure_one()
        domain = [
            ('product_id', 'in', products.ids),
            ('company_id', '=', self.company_id.id),
            ('create_date', operator, at_datetime),
        ]
        svl_sudo = self.env['stock.valuation.layer'].sudo()
        totals = {
            product.id: (quantity, value)
            for product, quantity, value in svl_sudo._read_group(
                domain, ['product_id'], ['quantity:sum', 'value:sum'])
        }
        unit_costs = {}
        without_stock = []
        for product in products:
            quantity, value = totals.get(product.id, (0.0, 0.0))
            if float_compare(quantity, 0, precision_rounding=product.uom_id.rounding) > 0:
                unit_costs[product.id] = value / quantity
            else:
                without_stock.append(product)
        for product in without_stock:
            last_layer = svl_sudo.search(
                [('product_id', '=', product.id), ('quantity', '!=', 0)] + domain[1:],
                order='create_date desc, id desc', limit=1,
            )
            unit_costs[product.id] = last_layer.unit_cost if last_layer else product.standard_price
        return unit_costs

    def _get_moves_unit_cost(self, moves, date_end):
        """Return {move: unit cost} from the valuation layers of the valued moves

        Moves done before stock_account was installed have no layer: they are left out so that
        the caller falls back on the cost at their date.
        """
        self.ensure_one()
        layer_groups = self.env['stock.valuation.layer'].sudo()._read_group(
            [
                ('stock_move_id', 'in', moves.ids),
                ('company_id', '=', self.company_id.id),
                ('create_date', '<', date_end),
            ],
            ['stock_move_id'], ['quantity:sum', 'value:sum'],
        )
        return {
            move: value / quantity
            for move, quantity, value in layer_groups
            if quantity
        }

    def _prepare_line_vals(self, line_type, product, **kwargs):
        """Prepare values for stock card line"""
        vals = {
            'wizard_id': self.id,
            'line_type': line_type,
            'product_id': product.id if product else False,
            'date': kwargs.get('date'),
            'reference': kwargs.get('reference', ''),
            'source_document': kwargs.get('source_document', ''),
            'partner_id': kwargs.get('partner_id'),
            'qty_in': kwargs.get('qty_in', 0.0),
            'qty_out': kwargs.get('qty_out', 0.0),
            'balance': kwargs.get('balance', 0.0),
            'initial_balance': kwargs.get('initial_balance', 0.0),
            'unit_cost': kwargs.get('unit_cost', 0.0),
            'value_in': kwargs.get('value_in', 0.0),
            'value_out': kwargs.get('value_out', 0.0),
            'balance_value': kwargs.get('balance_value', 0.0),
            'location_id': kwargs.get('location_id'),
            'location_dest_id': kwargs.get('location_dest_id'),
            'move_id': kwargs.get('move_id'),
            'move_line_id': kwargs.get('move_line_id'),
            'sequence': kwargs.get('sequence', 10),
        }
        return vals

    def _generate_stock_card_data(self):
        """Generate stock card data for all selected products"""
        self.ensure_one()
        self.line_ids.unlink()

        locations = self._get_locations()
        products = self._get_products().with_company(self.company_id)

        if not products:
            raise UserError(_('No products found matching the criteria.'))

        date_start, date_end = self._get_datetime_range()
        opening_balances = self._get_opening_balances(products, locations, date_start)
        transactions = self._get_transactions(products, locations, date_start, date_end)
        transactions_by_product = transactions.grouped('product_id')

        moves_unit_cost = self._get_moves_unit_cost(transactions.move_id, date_end)
        opening_costs = self._get_unit_costs_at(
            products.filtered(lambda p: opening_balances[p.id]), '<', date_start)
        company_partner = self.company_id.partner_id

        lines_data = []
        location_ids = set(locations.ids)
        if self.group_by == 'category':
            products = products.sorted(lambda p: (p.categ_id.complete_name or '', p.name))

        sequence = 0
        for product in products:
            opening_qty = opening_balances[product.id]
            opening_cost = opening_costs.get(product.id, 0.0)
            opening_value = opening_qty * opening_cost

            transactions = transactions_by_product.get(product, self.env['stock.move.line'])

            if not transactions and not self.include_zero_movements and opening_qty == 0:
                continue

            running_balance = opening_qty
            running_value = opening_value
            unit_cost = opening_cost

            sequence += 1
            lines_data.append(self._prepare_line_vals(
                'opening',
                product,
                date=self.date_from,
                reference=_('Opening Balance'),
                balance=opening_qty,
                unit_cost=opening_cost,
                balance_value=opening_value,
                sequence=sequence,
            ))

            for move_line in transactions:
                src_inside = move_line.location_id.id in location_ids
                dest_inside = move_line.location_dest_id.id in location_ids
                if src_inside == dest_inside:
                    # Internal transfer between the selected locations
                    continue

                qty = move_line.quantity_product_uom
                qty_in = qty if dest_inside else 0.0
                qty_out = qty if src_inside else 0.0
                move = move_line.move_id
                day = fields.Date.context_today(self, move_line.date)

                # Moves entering or leaving the company carry their valuation layers. Transfers
                # between internal locations (not valued) leave at the card's average cost
                # and arrive at the company cost of the moment.
                unit_cost = moves_unit_cost.get(move)
                if unit_cost is None:
                    if move_line.owner_id and move_line.owner_id != company_partner:
                        # Consigned stock does not belong to the company valuation
                        unit_cost = 0.0
                    elif qty_out and running_balance > 0:
                        unit_cost = running_value / running_balance
                    else:
                        unit_cost = self._get_unit_costs_at(product, '<=', move_line.date)[product.id]

                initial_balance = running_balance
                running_balance += qty_in - qty_out

                value_in = qty_in * unit_cost
                value_out = qty_out * unit_cost
                running_value += value_in - value_out

                sequence += 1
                lines_data.append(self._prepare_line_vals(
                    'transaction',
                    product,
                    date=day,
                    reference=move.picking_id.name or move.reference or move.display_name,
                    source_document=move.origin or '',
                    partner_id=move.partner_id.id or move_line.picking_partner_id.id,
                    initial_balance=initial_balance,
                    qty_in=qty_in,
                    qty_out=qty_out,
                    balance=running_balance,
                    unit_cost=unit_cost,
                    value_in=value_in,
                    value_out=value_out,
                    balance_value=running_value,
                    location_id=move_line.location_id.id,
                    location_dest_id=move_line.location_dest_id.id,
                    move_id=move.id,
                    move_line_id=move_line.id,
                    sequence=sequence,
                ))

            sequence += 1
            lines_data.append(self._prepare_line_vals(
                'closing',
                product,
                date=self.date_to,
                reference=_('Closing Balance'),
                initial_balance=opening_qty,
                balance=running_balance,
                unit_cost=running_value / running_balance if running_balance > 0 else unit_cost,
                balance_value=running_value,
                sequence=sequence,
            ))

        if not lines_data:
            raise UserError(_('No stock movements found for the selected criteria.'))

        self.env['stock.card.line'].create(lines_data)

        return True

    def _get_summary_rows(self):
        """Return one summary dict per product, used by the PDF and Excel reports"""
        self.ensure_one()
        transactions_by_product = self.line_ids.filtered(lambda l: l.line_type == 'transaction').grouped('product_id')
        rows = []
        for line in self.line_ids.filtered(lambda l: l.line_type == 'closing'):
            transactions = transactions_by_product.get(line.product_id, self.env['stock.card.line'])
            rows.append({
                'product': line.product_id.display_name,
                'category': line.categ_id.complete_name or '',
                'uom': line.uom_id.name,
                'uom_id': line.uom_id.id,
                'initial_balance': line.initial_balance,
                'total_in': sum(transactions.mapped('qty_in')),
                'total_out': sum(transactions.mapped('qty_out')),
                'balance': line.balance,
                'unit_cost': line.unit_cost,
                'balance_value': line.balance_value,
            })
        return rows

    def _get_summary_totals(self, rows):
        """Totals of the summary rows. Quantities are only summed when all products share one UoM."""
        self.ensure_one()
        totals = {'balance_value': sum(row['balance_value'] for row in rows)}
        if len({row['uom_id'] for row in rows}) == 1:
            for key in ('initial_balance', 'total_in', 'total_out', 'balance'):
                totals[key] = sum(row[key] for row in rows)
        return totals

    def action_view_report(self):
        """Generate and view the stock card report"""
        self.ensure_one()
        self._generate_stock_card_data()

        action = {
            'name': _('Stock Card Report'),
            'type': 'ir.actions.act_window',
            'res_model': 'stock.card.line',
            'view_mode': 'list,pivot',
            'views': [
                (self.env.ref('fs_stock_card.view_stock_card_line_list').id, 'list'),
                (self.env.ref('fs_stock_card.view_stock_card_line_pivot').id, 'pivot'),
            ],
            'search_view_id': [self.env.ref('fs_stock_card.view_stock_card_line_search').id],
            'domain': [('wizard_id', '=', self.id)],
            'context': {
                'search_default_group_by_product': self.group_by == 'product',
                'search_default_group_by_category': self.group_by == 'category',
            },
            'target': 'current',
        }

        return action

    def action_generate_pdf(self):
        """Generate PDF report"""
        self.ensure_one()
        self._generate_stock_card_data()

        return self.env.ref('fs_stock_card.action_report_stock_card').report_action(self)

    def action_generate_excel(self):
        """Generate Excel report"""
        self.ensure_one()

        if not xlsxwriter:
            raise UserError(_('xlsxwriter library is required for Excel export. Please install it.'))

        self._generate_stock_card_data()

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        worksheet = workbook.add_worksheet('Stock Card')

        header_format = workbook.add_format({
            'bold': True,
            'align': 'center',
            'valign': 'vcenter',
            'bg_color': '#875A7B',
            'font_color': 'white',
            'border': 1,
        })

        title_format = workbook.add_format({
            'bold': True,
            'font_size': 14,
            'align': 'center',
        })

        number_format = workbook.add_format({
            'num_format': '#,##0.00',
            'align': 'right',
            'border': 1,
        })

        text_format = workbook.add_format({
            'align': 'left',
            'border': 1,
        })

        total_format = workbook.add_format({
            'bold': True,
            'bg_color': '#F3E5F5',
            'border': 1,
            'num_format': '#,##0.00',
        })

        worksheet.merge_range('A1:I1', _('Stock Card Summary Report'), title_format)
        worksheet.write('A2', _('Period: %(date_from)s to %(date_to)s', date_from=self.date_from, date_to=self.date_to))
        worksheet.write('A3', _('Location: %s', self.location_id.complete_name))
        worksheet.write('A4', _('Company: %s', self.company_id.name))

        headers = [
            _('Product'), _('Category'), _('UoM'), _('Initial Balance'), _('Total In'), _('Total Out'),
            _('Closing Balance'), _('Unit Cost'), _('Balance Value'),
        ]

        col_widths = [35, 25, 10, 15, 15, 15, 15, 15, 18]
        for col, width in enumerate(col_widths):
            worksheet.set_column(col, col, width)

        row = 5
        for col, header in enumerate(headers):
            worksheet.write(row, col, header, header_format)

        rows = self._get_summary_rows()
        totals = self._get_summary_totals(rows)
        columns = ['product', 'category', 'uom', 'initial_balance', 'total_in', 'total_out',
                   'balance', 'unit_cost', 'balance_value']

        row += 1
        for data in rows:
            for col, key in enumerate(columns):
                worksheet.write(row, col, data[key], text_format if col < 3 else number_format)
            row += 1

        row += 1
        worksheet.write(row, 0, _('TOTALS:'), total_format)
        for col, key in enumerate(columns[1:], start=1):
            worksheet.write(row, col, totals.get(key, ''), total_format)

        workbook.close()
        self.write({
            'excel_file': base64.b64encode(output.getvalue()),
            'excel_filename': f'Stock_Card_Report_{self.date_from}_{self.date_to}.xlsx',
        })
        output.close()

        return {
            'type': 'ir.actions.act_url',
            'url': (
                f'/web/content?model={self._name}&id={self.id}&field=excel_file'
                '&filename_field=excel_filename&download=true'
            ),
            'target': 'new',
        }
