{
    'name': 'POS Receipt Customization - Rayanna',
    'version': '1.0',
    'category': 'Sales/Point of Sale',
    'summary': 'Customized POS receipt for Rayanna restaurant',
    'description': 'Customized POS receipt for Rayanna restaurant based on user design.',
    'depends': ['point_of_sale'],
    'data': [],
    'assets': {
        'point_of_sale._assets_pos': [
            'pos_recite_rayanna/static/src/xml/OrderReceipt.xml',
            'pos_recite_rayanna/static/src/css/pos_receipt.css',
            'pos_recite_rayanna/static/src/js/OrderReceipt.js',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
