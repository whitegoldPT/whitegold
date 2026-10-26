from datetime import date, datetime

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestStockCard(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env['stock.warehouse'].create({'name': 'Stock Card WH', 'code': 'SCWH'})
        cls.stock_location = cls.warehouse.lot_stock_id
        cls.shelf = cls.env['stock.location'].create({'name': 'Shelf', 'location_id': cls.stock_location.id})
        cls.supplier_location = cls.env.ref('stock.stock_location_suppliers')
        cls.customer_location = cls.env.ref('stock.stock_location_customers')
        cls.uom_unit = cls.env.ref('uom.product_uom_unit')
        cls.uom_dozen = cls.env.ref('uom.product_uom_dozen')
        cls.category = cls.env['product.category'].create({'name': 'Stock Card Category'})
        cls.product = cls.env['product.product'].create({
            'name': 'Stock Card Product',
            'is_storable': True,
            'uom_id': cls.uom_unit.id,
            'categ_id': cls.category.id,
            'standard_price': 10.0,
        })
        cls.stock_user = new_test_user(cls.env, login='stock_card_user', groups='stock.group_stock_user', tz='Asia/Jakarta')

    def _done_move(self, src, dest, qty, when, uom=None, product=None, unit_cost=None):
        vals = {
            'name': 'Stock card test move',
            'product_id': (product or self.product).id,
            'product_uom_qty': qty,
            'product_uom': (uom or self.uom_unit).id,
            'location_id': src.id,
            'location_dest_id': dest.id,
        }
        if unit_cost is not None:
            vals['price_unit'] = unit_cost
        move = self.env['stock.move'].create(vals)
        move._action_confirm()
        move.quantity = qty
        move.picked = True
        move._action_done()
        self.assertEqual(move.state, 'done')
        move.write({'date': when})
        move.move_line_ids.write({'date': when})
        # Valuation layers are dated by create_date
        self.env.cr.execute(
            "UPDATE stock_valuation_layer SET create_date = %s WHERE stock_move_id = %s", (when, move.id))
        self.env['stock.valuation.layer'].invalidate_model(['create_date'])
        return move

    def _wizard(self, **vals):
        return self.env['stock.card.wizard'].with_user(self.stock_user).create({
            'date_from': date(2026, 3, 1),
            'date_to': date(2026, 3, 31),
            'location_id': self.stock_location.id,
            'product_ids': [(6, 0, self.product.ids)],
            **vals,
        })

    def test_balances_uom_and_period_bounds(self):
        # Before the period: opening balance of 10
        self._done_move(self.supplier_location, self.stock_location, 10, datetime(2026, 2, 20, 3, 0))
        # Received in dozens: must count as 24 units
        self._done_move(self.supplier_location, self.shelf, 2, datetime(2026, 3, 5, 3, 0), uom=self.uom_dozen)
        # Last day of the period at 21:00 Jakarta time (14:00 UTC) must be included
        self._done_move(self.stock_location, self.customer_location, 4, datetime(2026, 3, 31, 14, 0))
        # Internal transfer between selected locations is not a movement
        self._done_move(self.stock_location, self.shelf, 3, datetime(2026, 3, 10, 3, 0))
        # 2026-04-01 01:00 Jakarta time is 2026-03-31 18:00 UTC: outside the period
        self._done_move(self.stock_location, self.customer_location, 1, datetime(2026, 3, 31, 18, 0))

        wizard = self._wizard()
        action = wizard.action_view_report()
        self.assertEqual(action['res_model'], 'stock.card.line')

        lines = wizard.line_ids
        opening = lines.filtered(lambda l: l.line_type == 'opening')
        transactions = lines.filtered(lambda l: l.line_type == 'transaction').sorted('sequence')
        closing = lines.filtered(lambda l: l.line_type == 'closing')

        self.assertEqual(opening.balance, 10)
        self.assertEqual(transactions.mapped('qty_in'), [24, 0])
        self.assertEqual(transactions.mapped('qty_out'), [0, 4])
        self.assertEqual(transactions[-1].date, date(2026, 3, 31))
        self.assertEqual(closing.balance, 30)
        self.assertEqual(closing.balance_value, 300)

        rows = wizard._get_summary_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]['total_in'], rows[0]['total_out'], rows[0]['balance']), (24, 4, 30))

    def test_historical_average_cost(self):
        category = self.env['product.category'].create({
            'name': 'AVCO', 'property_cost_method': 'average', 'property_valuation': 'manual_periodic',
        })
        product = self.env['product.product'].create({
            'name': 'AVCO Product', 'is_storable': True, 'categ_id': category.id, 'standard_price': 10.0,
        })
        self._done_move(self.supplier_location, self.stock_location, 10, datetime(2026, 2, 10, 3, 0),
                        product=product, unit_cost=10)
        self._done_move(self.supplier_location, self.stock_location, 10, datetime(2026, 3, 5, 3, 0),
                        product=product, unit_cost=20)
        self._done_move(self.stock_location, self.customer_location, 5, datetime(2026, 3, 6, 3, 0),
                        product=product)
        # A cost change after the period must not change the reported values
        product.standard_price = 99.0

        wizard = self._wizard(product_ids=[(6, 0, product.ids)])
        wizard._generate_stock_card_data()
        opening = wizard.line_ids.filtered(lambda l: l.line_type == 'opening')
        transactions = wizard.line_ids.filtered(lambda l: l.line_type == 'transaction').sorted('sequence')
        closing = wizard.line_ids.filtered(lambda l: l.line_type == 'closing')

        self.assertEqual((opening.balance, opening.balance_value), (10, 100))
        self.assertEqual(transactions.mapped('value_in'), [200, 0])
        self.assertEqual(transactions.mapped('value_out'), [0, 75])
        self.assertEqual((closing.balance, closing.balance_value, closing.unit_cost), (15, 225, 15))

        # An internal transfer is not valued: it arrives at the company average cost of the moment
        self._done_move(self.stock_location, self.shelf, 4, datetime(2026, 3, 7, 3, 0), product=product)
        wizard = self._wizard(location_id=self.shelf.id, product_ids=[(6, 0, product.ids)])
        wizard._generate_stock_card_data()
        transaction = wizard.line_ids.filtered(lambda l: l.line_type == 'transaction')
        self.assertEqual((transaction.qty_in, transaction.value_in), (4, 60))

    def test_historical_standard_cost(self):
        product = self.env['product.product'].create({
            'name': 'Standard Product', 'is_storable': True, 'standard_price': 10.0,
        })
        # Starting from zero stock, received at a bill price that standard cost ignores
        self._done_move(self.supplier_location, self.stock_location, 10, datetime(2026, 3, 5, 3, 0),
                        product=product, unit_cost=50)
        # A standard price change after the period must not change the reported values
        product.standard_price = 99.0

        wizard = self._wizard(product_ids=[(6, 0, product.ids)])
        wizard._generate_stock_card_data()
        transaction = wizard.line_ids.filtered(lambda l: l.line_type == 'transaction')
        closing = wizard.line_ids.filtered(lambda l: l.line_type == 'closing')
        self.assertEqual((transaction.unit_cost, transaction.value_in), (10, 100))
        self.assertEqual(closing.balance_value, 100)

        # The next period opens at the standard price of its start
        wizard = self._wizard(date_from=date(2026, 4, 1), date_to=date(2026, 4, 30),
                              product_ids=[(6, 0, product.ids)])
        wizard._generate_stock_card_data()
        opening = wizard.line_ids.filtered(lambda l: l.line_type == 'opening')
        self.assertEqual((opening.balance, opening.balance_value), (10, 100))

    def test_later_layers_and_consignment(self):
        receipt = self._done_move(self.supplier_location, self.stock_location, 10, datetime(2026, 3, 5, 3, 0))
        # A landed cost style layer (value only) created after the period
        layer = self.env['stock.valuation.layer'].create({
            'product_id': self.product.id,
            'company_id': self.env.company.id,
            'stock_move_id': receipt.id,
            'quantity': 0,
            'value': 500,
        })
        self.env.cr.execute(
            "UPDATE stock_valuation_layer SET create_date = %s WHERE id = %s", (datetime(2026, 5, 2), layer.id))
        self.env['stock.valuation.layer'].invalidate_model(['create_date'])

        # Consigned goods are not part of the company valuation
        consignment = self.env['stock.move'].create({
            'name': 'Consignment',
            'product_id': self.product.id,
            'product_uom_qty': 3,
            'product_uom': self.uom_unit.id,
            'location_id': self.supplier_location.id,
            'location_dest_id': self.stock_location.id,
        })
        consignment._action_confirm()
        consignment.quantity = 3
        consignment.move_line_ids.owner_id = self.env['res.partner'].create({'name': 'Consignor'})
        consignment.picked = True
        consignment._action_done()
        consignment.write({'date': datetime(2026, 3, 6, 3, 0)})
        consignment.move_line_ids.write({'date': datetime(2026, 3, 6, 3, 0)})

        self.product.active = False
        wizard = self._wizard(product_ids=False)
        wizard._generate_stock_card_data()
        transactions = wizard.line_ids.filtered(lambda l: l.line_type == 'transaction').sorted('sequence')
        self.assertEqual(transactions.mapped('qty_in'), [10, 3])
        self.assertEqual(transactions.mapped('value_in'), [100, 0])

    def test_totals_skip_mixed_uom(self):
        product_dozen = self.env['product.product'].create({
            'name': 'Dozen Product', 'is_storable': True, 'uom_id': self.uom_dozen.id, 'standard_price': 5.0,
        })
        self._done_move(self.supplier_location, self.stock_location, 5, datetime(2026, 3, 5, 3, 0))
        self._done_move(self.supplier_location, self.stock_location, 2, datetime(2026, 3, 5, 3, 0),
                        uom=self.uom_dozen, product=product_dozen)
        wizard = self._wizard(product_ids=[(6, 0, (self.product | product_dozen).ids)])
        wizard._generate_stock_card_data()
        totals = wizard._get_summary_totals(wizard._get_summary_rows())
        self.assertEqual(totals, {'balance_value': 60})

        wizard = self._wizard()
        wizard._generate_stock_card_data()
        totals = wizard._get_summary_totals(wizard._get_summary_rows())
        self.assertEqual(totals['total_in'], 5)

    def test_without_child_locations(self):
        self._done_move(self.supplier_location, self.shelf, 5, datetime(2026, 3, 5, 3, 0))
        self._done_move(self.supplier_location, self.stock_location, 2, datetime(2026, 3, 6, 3, 0))
        wizard = self._wizard(include_child_locations=False)
        wizard._generate_stock_card_data()
        closing = wizard.line_ids.filtered(lambda l: l.line_type == 'closing')
        self.assertEqual(closing.balance, 2)

    def test_move_without_picking_reference(self):
        self._done_move(self.supplier_location, self.stock_location, 5, datetime(2026, 3, 5, 3, 0))
        wizard = self._wizard()
        wizard._generate_stock_card_data()
        transaction = wizard.line_ids.filtered(lambda l: l.line_type == 'transaction')
        self.assertTrue(transaction.reference)

    def test_category_grouping(self):
        other = self.env['product.product'].create({
            'name': 'Second Product', 'is_storable': True, 'categ_id': self.category.id,
        })
        self._done_move(self.supplier_location, self.stock_location, 5, datetime(2026, 3, 5, 3, 0))
        wizard = self._wizard(filter_by='category', product_ids=False, categ_ids=[(6, 0, self.category.ids)],
                              group_by='category', include_zero_movements=True)
        action = wizard.action_view_report()
        self.assertTrue(action['context']['search_default_group_by_category'])
        self.assertEqual(wizard.line_ids.filtered(lambda l: l.line_type == 'closing').product_id, self.product | other)

    def test_skip_product_without_movement(self):
        other = self.env['product.product'].create({
            'name': 'Idle Product', 'is_storable': True, 'categ_id': self.category.id,
        })
        self._done_move(self.supplier_location, self.stock_location, 5, datetime(2026, 3, 5, 3, 0))
        wizard = self._wizard(product_ids=[(6, 0, (self.product | other).ids)])
        wizard._generate_stock_card_data()
        self.assertEqual(wizard.line_ids.product_id, self.product)

    def test_other_user_cannot_read(self):
        self._done_move(self.supplier_location, self.stock_location, 5, datetime(2026, 3, 5, 3, 0))
        wizard = self._wizard()
        wizard._generate_stock_card_data()
        other_user = new_test_user(self.env, login='stock_card_other', groups='stock.group_stock_user')
        self.assertFalse(self.env['stock.card.line'].with_user(other_user).search([('wizard_id', '=', wizard.id)]))
        with self.assertRaises(AccessError):
            wizard.with_user(other_user).read(['date_from'])

    def test_reports_render(self):
        self._done_move(self.supplier_location, self.stock_location, 5, datetime(2026, 3, 5, 3, 0))
        wizard = self._wizard()
        wizard._generate_stock_card_data()
        html, _report_type = self.env['ir.actions.report'].with_user(self.stock_user)._render_qweb_html(
            'fs_stock_card.action_report_stock_card', wizard.ids)
        self.assertIn(b'Stock Card Product', html)

        action = wizard.action_generate_excel()
        self.assertEqual(action['type'], 'ir.actions.act_url')
        self.assertTrue(wizard.excel_file)
        self.assertTrue(wizard.excel_filename.endswith('.xlsx'))

    def test_no_movements_raises(self):
        wizard = self._wizard()
        with self.assertRaises(UserError):
            wizard._generate_stock_card_data()

    def test_invalid_dates(self):
        with self.assertRaises(ValidationError):
            self._wizard(date_from=date(2026, 4, 1))
