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
    'name': 'MRP OverHead Costing Base',
    'version': '8.0.1',
    'category': 'Manufacturing',
    "author": 'Zero Systems',
    "company": 'Zero for Information Systems',
    "website": "https://www.erpzero.com",
    "email": "sales@erpzero.com",
    "sequence": 0,
    'license': 'OPL-1',
    'summary': """base module for zero systems advanced MRP OverHead Costs""",
    'descriaption': """ 
        base module for zero systems advanced MRP fixed and OverHead Costs
        """,
    'depends': ['product','account'],
    'data': [
        'security/ir.model.access.csv',
        'views/overhead_type.xml',
    ],
    "price": 75.00,
    "currency": 'EUR',
    'images': ['static/description/icon.png'],
    'pre_init_hook': 'pre_init_check',
    'installable': True,
    'auto_install': False,
    'application': False,
}
