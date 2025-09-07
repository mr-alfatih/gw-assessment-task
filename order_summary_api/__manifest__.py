# order_summary_api/__manifest__.py
{
    'name': 'Order Summary API',
    'version': '18.0.1.0.0',
    'summary': 'Provides a high-performance API for order summaries with real-time updates.',
    'author': 'ALFATIH MOHAMED',
    'category': 'Extra Tools',
    'depends': [
        'web',
        'sale_management',
        'stock',
        'mrp',
    ],
    'data': [
        # 'security/ir.model.access.csv',
        'views/order_summary_menu.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'order_summary_api/static/src/js/order_summary_popup.js',
            'order_summary_api/static/src/xml/templates.xml',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
