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
    'name': 'odoo Enhancement MRP Unbuild Order with Accounting',
    'version': '8.0.3',
    'category': 'Manufacturing',
    "author": 'Zero Systems',
    "company": 'Zero for Information Systems',
    "website": "https://www.erpzero.com",
    "email": "sales@erpzero.com",
    'live_test_url': 'https://youtu.be/4ezSYsTybLk',
    "sequence": 0,
    'license': 'OPL-1',
    'summary': 'FIX MRP Unbuild Order Business cycle with KIT products',
    'description': """
    
        When making a MRP Unbuild Order, it is one of the standard errors of Odoo as the following:

        1- It allows the selection of Products that do not have a BOM, i.e. they do not have raw material to dismantle into

        2- It allows the dismantling of Products whose BOM type is "KIT" and whose inventory balance is zero, and here inventory errors occur, as the inventory balance is negative for an product that cannot be produced "according to the type of the list of materials", so it cannot appear in an inventory balance at all unless, before dismantling this product, it is received in storage location in its final form as a final product and not its components are received, and its balance is equal to or greater than the quantity required to be dismantled.

        but We have solved these problems as follows:
        1- Create a domain when selecting a product that is to be disassembled into its raw materials by displaying only products that have a BOM only.
        2- When selecting an product whose BOM is of the type "KIT" and does not have a stock balance that allows the operation, a message appears to prevent the user and alerts him that the stock balance does not allow the disassembly order to be executed for this product.
""",
    'data': [
        'views/view.xml',

    ],
    'depends': ['account','mrp_account'],
    "price": 25.00,
    "currency": 'EUR',
    'images': ['static/description/icon.png'],
    'pre_init_hook': 'pre_init_check',
    'post_init_hook': '_configure_journals',
    'installable': True,
    'auto_install': False,
    'application': False,
}
