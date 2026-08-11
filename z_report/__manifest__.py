{
    'name': 'Z Report',
    'version': '18.0.1.0.0',
    'category': 'Reports',
    'summary': 'Z Report for Sales',
    'author': 'Peak Dev',
    'website': 'https://peakdev.tech',
    'depends': ['base', 'point_of_sale'],
    'data': [
        'security/ir.model.access.csv',
        'reports/z_report_template.xml',
        'wizard/z_report_wizard_view.xml',
    ],
    'installable': True,
    'application': False,
}