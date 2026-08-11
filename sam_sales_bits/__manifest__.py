{
    "name": "SAM Sales External Link Hide",
    "version": '18.0.1.0.0',
    'category': 'Services',
    "sequence": 14,
    "summary": """
        This module is for hide external link in sale order line product field. Because sales module has used custom widget for M2O field widget.
    """,
    "description": """ 
        This module is for hide external link in sale order line product field. Because sales module has used custom widget for M2O field widget.
    """,
    "author": "Terabits Technolab",
    "website": "https://www.terabits.xyz",
    "depends": ["sale"],
    "license": "OPL-1",
    "price": "",
    "currency": "USD",
    "data": [],
    "assets": {
        "web.assets_backend": [
            '/sam_sales_bits/static/src/js/sale_product_field.js'
        ],
    },
    "images": ["static/description/banner.gif"],
    "installable": True,
    "auto_install": False,
    "application": True,
}
