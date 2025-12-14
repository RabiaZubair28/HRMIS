{
    'name': "HRMIS User Profiles Updates",
    'version': "1.0",
    'summary': "Staff Personal Information Profile - Read Only for Employees",
    'category': 'Human Resources',
    'author': "Humza Aqeel Shaikh",
    'depends': ['hr', 'district_facility'],
    'data': [
        'security/ir.model.access.csv',
        'views/hrmis_user_profile_views.xml',
        'views/hr_employee_inherit.xml',
    ],
    'installable': True,
    'application': False,
}
