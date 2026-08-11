# -*- coding: utf-8 -*-
#################################################################################
# Author      : Zero For Information Systems (<www.erpzero.com>)
# Copyright(c): 2016-Zero For Information Systems
# All Rights Reserved.
#
# This program is copyright property of the author mentioned above.
# You can`t redistribute it and/or modify it.
#
#################################################################################


{
    'name': 'KIT Products Sale Margin',
    'version': '8.0.1',
    'category': 'Manufacturing',
    "author": 'Zero Systems',
    "company": 'Zero for Information Systems',
    "website": "https://www.erpzero.com",
    "email": "sales@erpzero.com",
    'live_test_url': 'https://youtu.be/YlUG9GG_TkA',
    "sequence": 0,
    'license': 'OPL-1',
    'summary': 'KIT Products Fix Sale Margin',
    'description': """
        odoo  does not, as a standard, automatically update the cost of the KIT product. Therefore,
     if its standard cost is zero or any value is not updated, the profitability of the KIT product will always be an error.

    But with this application, when the item is selected in the sales order, 
    the system will automatically update the cost of the KIT product and come with an exact cost according to the latest cost of
     its internal components.
""",
    'data': [

    ],
    'depends': ['sale_margin','sale_mrp'],
    "price": 15.00,
    "currency": 'EUR',
    'images': ['static/description/sale_kit_margin.png'],
    'pre_init_hook': 'pre_init_check',
    'installable': True,
    'auto_install': False,
    'application': False,
}
