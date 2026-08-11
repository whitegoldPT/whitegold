# -*- coding: utf-8 -*-
{
    'name': 'POS Customer Create Access Rights',
    'version': '18.0.1.0.0',
    'category': 'Point of Sale',
    'summary': 'Control access rights for creating new customers in POS',
    'description': """
POS Customer Create Access Rights (Odoo 18)
============================================
Restricts who can create new customers from the Point of Sale.

* Adds security group: "POS / Create Customer"
* Only users in this group can create new customers from POS
* Server-side validation also blocks bypass attempts via RPC
* POS Manager users automatically inherit this permission
* Uses lightweight RPC permission check — no POS data-loader interference
    """,
    'author': 'Ahmed',
    'website': '',
    'depends': ['point_of_sale'],
    'data': [
        'security/pos_security_groups.xml',
        'security/ir.model.access.csv',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'pos_customer_create_access/static/src/js/partner_list.js',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
