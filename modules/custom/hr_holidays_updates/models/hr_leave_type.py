from odoo import models, fields, api

class HrLeaveType(models.Model):
    _inherit = 'hr.leave.type'

   
    # Gender restriction field
    allowed_gender = fields.Selection([
        ('all', 'All Genders'),
        ('male', 'Male Only'),
        ('female', 'Female Only'),
    ], string="Allowed Gender", default='all')

    support_document_note = fields.Char(
        string="Supporting Document Requirement",
        help="Short instruction shown to employees about which supporting document is required.",
    )

    min_service_months = fields.Integer(
        string="Minimum Service (Months)",
        default=0,
        help="Minimum length of service required to request this leave type, based on employee joining date.",
    )

    max_days_per_request = fields.Float(
        string="Max Duration Per Request (Days)",
        default=0.0,
        help="Maximum number of days allowed in a single request for this leave type. 0 means no limit.",
    )
    max_days_per_month = fields.Float(
        string="Max Duration Per Month (Days)",
        default=0.0,
        help="Maximum total days allowed per calendar month for this leave type. 0 means no limit.",
    )
    max_days_per_year = fields.Float(
        string="Max Duration Per Year (Days)",
        default=0.0,
        help="Maximum total days allowed per calendar year for this leave type. 0 means no limit.",
    )
    max_times_in_service = fields.Integer(
        string="Max Times In Service",
        default=0,
        help="Maximum number of times this leave type can be taken over the employee's service. 0 means no limit.",
    )

    @api.model
    def apply_support_document_rules(self):
        """
        Ensure the listed leave types require a supporting document.
        This is safe to run on every module upgrade.
        """
        rules = {
            # User-requested rules
            "Leave Without Pay (EOL)": "Written request should be given.",
            "Leave Without Pay": "Written request should be given.",
            "Ex-Pakistan Leave": "Government Permission Letter.",
            "Special Leave (Accident/Injury)": "Medical Certificate.",
            "Special Leave (Accident / Injury)": "Medical Certificate.",
            "Special Leave (Quarantine)": "Quarantine order.",
            "Study Leave": "Admission Letter & Course Details.",
            "Medical Leave (Long Term)": "Medical Certificate.",
            "Leave Preparatory to Retirement (LPR)": "Fitness Certificate.",
            "LPR": "Fitness Certificate.",
        }

        for leave_type_name, note in rules.items():
            leave_types = self.search([('name', '=ilike', leave_type_name)])
            if not leave_types:
                continue
            leave_types.write({
                'support_document': True,
                'support_document_note': note,
            })

    @api.model
    def apply_service_eligibility_rules(self):
        """
        Ensure the requested leave types enforce minimum service requirements.
        This is safe to run on every module upgrade.
        """
        rules = {
            # User-requested rules:
            # - Earned leave (full pay): >= 12 months
            # - Study leave: >= 5 years (60 months)
            "Earned Leave With Pay": 12,
            "Earned Leave (Full Pay)": 12,
            "Earned Leave": 12,
            "Study Leave": 60,
        }

        for leave_type_name, months in rules.items():
            leave_types = self.search([('name', '=ilike', leave_type_name)])
            if not leave_types:
                continue
            leave_types.write({'min_service_months': months})

    @api.model
    def apply_max_duration_rules(self):
        """
        Apply max-duration defaults based on the provided policy table.
        Safe to run on every module upgrade.
        """
        rules = {
            # Casual Leave: 2 days/month OR 24 days/year
            "Casual Leave (CL)": {"max_days_per_month": 2.0, "max_days_per_year": 24.0},
            "Casual Leave": {"max_days_per_month": 2.0, "max_days_per_year": 24.0},

            # Earned Leave (Full Pay): 48 days/year (accrues separately; this is a request cap)
            "Earned Leave (Full Pay)": {"max_days_per_year": 48.0},
            "Earned Leave With Pay": {"max_days_per_year": 48.0},
            "Earned Leave": {"max_days_per_year": 48.0},

            # Leave on Half Pay: 20 days/year
            "Leave On Half Pay": {"max_days_per_year": 20.0},
            "Leave on Half Pay": {"max_days_per_year": 20.0},

            # Maternity: 90 days per request, max 3 times in service
            "Maternity Leave": {"max_days_per_request": 90.0, "max_times_in_service": 3},

            # Paternity: 7 days per request, max 2 times in service
            "Paternity Leave": {"max_days_per_request": 7.0, "max_times_in_service": 2},

            # Study: up to 2 years (extendable by 1) -> enforce max 3 years per request
            "Study Leave": {"max_days_per_request": 1095.0},

            # LPR: max 365 days
            "Leave Preparatory to Retirement (LPR)": {"max_days_per_request": 365.0},
            "LPR": {"max_days_per_request": 365.0},
        }

        for leave_type_name, vals in rules.items():
            leave_types = self.search([('name', '=ilike', leave_type_name)])
            if not leave_types:
                continue
            leave_types.write(vals)

    @api.model
    def apply_skip_allocation_rules(self):
        """
        Allow employees to request leaves without prior allocations.
        This sets requires_allocation='no' on all leave types (safe on upgrade).
        """
        self.search([]).write({'requires_allocation': 'no'})

    # Example: override a method (keep original functionality)
    def _check_allocation(self, employee_id, request_date_from, request_date_to):
        res = super()._check_allocation(employee_id, request_date_from, request_date_to)
        # Add your custom validation logic here
        return res
    
   