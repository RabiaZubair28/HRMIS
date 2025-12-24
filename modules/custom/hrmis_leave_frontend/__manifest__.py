# -*- coding: utf-8 -*-
{
    "name": "HRMIS Leave Frontend",
    "version": "1.0.0",
    "summary": "Website frontend UI for HRMIS leave services",
    "category": "Human Resources/Time Off",
    "license": "LGPL-3",
    "depends": [
        "website",
        "hr",
        "hr_holidays",
        "hrmis_user_profiles_updates",
        "district_facility",
        "ohrms_holidays_approval",
        "hr_holidays_updates",
    ],
    "data": [
        "views/templates.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "hrmis_leave_frontend/static/src/scss/hrmis_leave_frontend.scss",
            "hrmis_leave_frontend/static/src/js/hrmis_leave_frontend.js",
        ],
    },
    "installable": True,
    "application": False,
}

