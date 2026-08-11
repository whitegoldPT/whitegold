{
    'name': "Disable Enterprise",
    'summary': """Disable Enterprise Code""",
    'description': """Disable Enterprise Code""",
    'author': "M Jamshaid",
    'category': 'Technical',
    'version': '1.0',
    "license": "AGPL-3",
    'depends': ['base', 'mail', 'web_enterprise'],
    'data': [
        'data/update_notification.xml',
        'data/service_cron.xml',
        
    ],
    'assets': {
        'web.assets_backend': [
            'disable_enterprise/static/src/webclient/**/*.xml',
    ],
    },
    "installable": True,
}
