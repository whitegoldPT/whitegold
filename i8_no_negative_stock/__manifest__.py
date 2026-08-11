# -*- coding: utf-8 -*-
{
    'name': "No Negative Stock (Sales & POS)",
    'summary': "Block selling out-of-stock products in Sales and POS",
    'description': """
        This addon is to restrict sale of out-of-stock product in Sales and PoS app.
    """,
    'version': "18.0.1.0.0",
    'author': "i8CLOUD Consulting",
    'company': 'i8CLOUD Consulting',
    'maintainer': 'i8CLOUD Consulting',
    'website': 'http://i8cloudconsulting.com',
    'support': 'contact@i8cloudconsulting.com',
    'license': "LGPL-3",
    'category': "Inventory/Inventory",
    'depends': ["stock", "sale_management", "point_of_sale"],
    'data': [
        "security/ir.model.access.csv",
        "views/pos_config_views.xml",
    ],
    'assets': {
        "point_of_sale._assets_pos": [
            "i8_no_negative_stock/static/src/overrides/stock_block_pos.js",
            "i8_no_negative_stock/static/src/low_stock/low_stock_toast.js",
        ]
    },
    "images": ["static/description/banner.gif"],
    'installable': True,
    'application': False,
    'price': 0.00,
    'currency': 'USD',
}
