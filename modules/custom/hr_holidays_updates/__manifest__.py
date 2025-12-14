# -*- coding: utf-8 -*-
{
    'name': 'Time Off Custom',
    'version': '1.0',
    'summary': 'Extend HR Holidays with custom leave types and functionality',
    'description': 'Keeps full hr_holidays features and adds custom leave types or fields.',
    'category': 'Human Resources/Time Off',
    'depends': ['hr','hr_holidays','hrmis_user_profiles_updates'],  # Important: extend the built-in module
    'data': [
        'data/leave_type_data.xml',  # optional
        'views/hr_holidays_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
