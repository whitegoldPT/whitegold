{
    'name': 'Advanced POS Bundle Promotions',
    'version': '18.0.1.0',
    'category': 'Point of Sale',
    'summary': 'Mix & Match Bundle promotions with fixed price for POS',
    'description': """
        خصومات باقات Mix & Match في نقطة البيع:
        - تعريف باقات من منتجات مختارة
        - تطبيق سعر ثابت للباقة الواحدة
        - حساب الخصم تلقائياً عند اكتمال الباقة
        - دعم عدة باقات في نفس الطلب
    """,
    'author': 'Antigravity',
    'depends': ['point_of_sale', 'loyalty', 'pos_loyalty'],
    'data': [
        'security/ir.model.access.csv',
        'views/pos_promotion_views.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'pos_advanced_promotions/static/src/js/pos_promotion.js',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
