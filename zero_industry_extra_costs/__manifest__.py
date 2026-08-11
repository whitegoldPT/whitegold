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
    'name': 'Advanced MRP Costing and Accounting All in One',
    'version': '8.0.1',
    'category': 'Manufacturing',
    "author": 'Zero Systems',
    "company": 'Zero for Information Systems',
    "website": "https://www.erpzero.com",
    "email": "sales@erpzero.com",
    'live_test_url': 'https://youtu.be/Z_-1kBhFwkM',
    "sequence": 0,
    'license': 'OPL-1',
    'summary': """Manufacturing Process Costing with Variable OverHead and Accounting Entry""",
    'descriaption': """ 
        Manufacturing Process Costing in Odoo with Variable OverHead Costing By Extra Cost(Miscellaneous Overhead Costs ,Labour, Energy Costs,...)
        This module helps to calculate MRP OverHads cost of 
        manufacturing order  with Variable OverHead cost, labour cost and 
        overhead cost from components. It calculates both 
        estimated costing and real costing. Estimated costing is done on Bill of 
        Material-BOM and real costing calculated on manufacturing order based on 
        quantity consumption.
        """,
    'depends': ['product','account','mrp_account','stock_kit_produced_quantity','zero_industry_extra_costs_base'],
    'data': [
        'security/ir.model.access.csv',
        'views/mrp_bom_views.xml',
        'views/mrp_production_views.xml',
        'report/mrp_bom_cost_report_templates.xml',
        'report/mrp_production_cost_report_templates.xml',
        'report/mrp_production_deviation.xml',
        'report/mrp_production_estemated_to_complete.xml',
    ],
    "price": 275.00,
    "currency": 'EUR',
    'images': ['static/description/mrp_overhead.png'],
    'pre_init_hook': 'pre_init_check',
    'post_init_hook': '_configure_journals',
    'installable': True,
    'auto_install': False,
    'application': False,
}
