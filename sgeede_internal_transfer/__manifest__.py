# -*- encoding: utf-8 -*-
{
    'name': "SGEEDE Internal Transfer.",
    'version': '18.0.0.1.4',  # Updated version
    'category': 'Tools',
    'summary': """Odoo's enhanced advanced stock internal transfer module""",
    'description': """Odoo's enhanced advanced stock internal transfer module with transit tracking and partial receive handling""",
    'author': 'SGEEDE',
    'website': 'http://www.sgeede.com',
    'depends': ['account', 'stock', 'product'],
    'data': [
        'security/security.xml',
        'data/ir_sequence.xml',
        'security/ir.model.access.csv',
        'wizard/wizard_stock_internal_transfer_view.xml',
        'wizard/partial_receive_reason_wizard_view.xml',
        'views/stock_internal_transfer_view.xml',
        'views/stock_view.xml',
        'views/stock_transit_product_view.xml',
        'views/transit_products_report_view.xml',  # New report view
        'views/res_config_view.xml',
    ],
    'qweb': [],
    'demo_xml': [],
    'installable': True,
    'application': False,
    'auto_install': False,
    'price': 19.99,
    'currency': 'EUR',
    'images': [
        'images/main_screenshot.png',
        'images/sgeede.png'
    ],
}
