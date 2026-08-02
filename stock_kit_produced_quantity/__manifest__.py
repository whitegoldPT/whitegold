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
    'name': 'kit Produced Quantity Analysis',
    'version': '8.0.1',
    'category': 'Manufacturing',
    "author": 'Zero Systems',
    "company": 'Zero for Information Systems',
    "website": "https://www.erpzero.com",
    "email": "sales@erpzero.com",
    'live_test_url': 'https://youtube.com/playlist?list=PLXFpENL3b6WX_CbALF_zsmSuctiAjbosT&si=EckhhbSIArcP74oJ',
    "sequence": 0,
    'license': 'OPL-1',
    'summary': 'KIT Products Delivered Stock Analysis and fix KIT Stock out journal entry',
    'description': """
    KIT Products Delivered Stock Analysis and fix KIT Stock out journal entry.
""",
    'data': [
        'security/ir.model.access.csv',
        'views/view.xml',
        'reports/report_deliveryslip.xml',

    ],
    'depends': ['stock','mrp','sale_mrp'],
    "price": 135.00,
    "currency": 'EUR',
    'images': ['static/description/kit_products.png'],
    'pre_init_hook': 'pre_init_check',
    'installable': True,
    'auto_install': False,
    'application': False,
}
