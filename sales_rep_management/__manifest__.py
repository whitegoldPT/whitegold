{
    'name': 'Sales Representative Management',
    'version': '18.0.1.0.0',
    'category': 'Sales',
    'summary': 'Manage sales representatives, routes, visits, and collections',
    'description': """
        Sales Representative Management System
        =====================================

        This module provides comprehensive management for sales representatives including:
        * Route planning and management
        * Visit scheduling and tracking
        * Collection management
        * Daily reports and analytics
        * Multi-level approval workflow
        * Integration with Odoo sales and accounting

        Features:
        ---------
        * Create and assign daily routes to sales reps
        * Track visits and customer interactions
        * Manage collections with receipt uploads
        * Generate comprehensive reports
        * Role-based access control
        * Dashboard with KPI tracking
    """,
    'author': 'PUG',
    'website': 'https://pomounited.com',
    'depends': [
        'base',
        'sale',
        'account',
        'point_of_sale',
        'contacts',
        'hr',
        'stock',
        'sale_stock',
        'sale_loyalty',
        'employees_fleet_license',
        'spd_leaflet_map',
    ],
    'external_dependencies': {
        'python': ['python-dateutil'],
    },
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        
        'data/sequence_data.xml',
        'data/cron_jobs.xml',
        
        'wizards/visit_result_wizard_views.xml',
        
        'views/sales_rep_views.xml',
        'views/route_views.xml',
        'views/visit_views.xml',
        'views/collection_views.xml',
        'views/dashboard_views.xml',
        'views/report_views.xml',
        'views/route_related_views.xml',
        'views/sales_rep_performance_report_views.xml',  # NEW FILE ADDEDc
        'views/menu_views.xml',
        'views/res_config_settings_views.xml',  # NEW
        'views/contact_views.xml',  # NEW
        'views/payment_method_views.xml',  # NEW
        'views/return_reason_views.xml',
        'views/sale_order_views.xml',
        'views/inherited_views.xml',
        'views/visit_types_views.xml',

        'reports/visit_report.xml',
        'reports/collection_report.xml',
        'reports/daily_report.xml',
    ],
    'demo': [
        'demo/demo_data.xml',
    ],
    'images': ['static/description/banner.png'],
    'installable': True,
    'auto_install': False,
    'application': True,
    'assets': {
        'web.assets_backend': [
            'sales_rep_management/static/src/scss/sales_rep_management.scss',
            'sales_rep_management/static/src/scss/time_picker.scss',
            'sales_rep_management/static/src/js/time_picker_widget.js',
            'sales_rep_management/static/src/js/visit_map.js',
            'sales_rep_management/static/src/js/contact_map.js',
            'sales_rep_management/static/src/xml/map_view.xml',
            'sales_rep_management/static/src/xml/contact_map_widget.xml',
            'sales_rep_management/static/src/xml/time_picker_templates.xml',
            'sales_rep_management/static/src/js/dashboard.js',
            'sales_rep_management/static/src/xml/dashboard.xml',
            'sales_rep_management/static/src/scss/dashboard.scss',
        ],
    },
    'license': 'LGPL-3',
}