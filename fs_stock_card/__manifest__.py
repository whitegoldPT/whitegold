{
    'name': 'Stock Card Report',
    'version': '18.0.1.1.0',
    'category': 'Inventory/Reporting',
    'summary': 'Stock Card / Product Card with Opening Balance, In/Out Movements, and Closing Balance',
    'description': """
Stock Card Report
=================
An essential tool for tracking the complete history of your inventory.

Features:
---------
* Detailed Stock Card / Product Card view
* Opening Balances, In/Out movements, and Closing Balances
* Historical values from the inventory valuation (Standard, AVCO, FIFO)
* Dynamic filtering by Product, Category, and Location (including child locations)
* Grouping options by Product or Category
* Professional PDF and Excel reports
* On-screen analysis with valid running balances
    """,
    'author': 'Farhan Sabili',
    'website': "https://www.linkedin.com/in/billylvn",
    'license': 'OPL-1',
    'depends': [
        'stock_account',
    ],
    'data': [
        'security/ir.model.access.csv',
        'security/stock_card_security.xml',
        'wizard/stock_card_wizard_views.xml',
        'report/stock_card_report.xml',
        'report/stock_card_report_template.xml',
        'views/stock_card_views.xml',
        'views/menu_views.xml',
    ],
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': True,
    'auto_install': False,
}
