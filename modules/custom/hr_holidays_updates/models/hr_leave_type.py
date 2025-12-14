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

    # Example: override a method (keep original functionality)
    def _check_allocation(self, employee_id, request_date_from, request_date_to):
        res = super()._check_allocation(employee_id, request_date_from, request_date_to)
        # Add your custom validation logic here
        return res
    
   