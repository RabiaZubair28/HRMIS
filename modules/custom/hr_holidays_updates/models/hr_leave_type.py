from odoo import models, fields, api

class HrLeaveType(models.Model):
    _inherit = 'hr.leave.type'

   
    # Gender restriction field
    allowed_gender = fields.Selection([
        ('all', 'All Genders'),
        ('male', 'Male Only'),
        ('female', 'Female Only'),
    ], string="Allowed Gender", default='all')

    # Example: override a method (keep original functionality)
    def _check_allocation(self, employee_id, request_date_from, request_date_to):
        res = super()._check_allocation(employee_id, request_date_from, request_date_to)
        # Add your custom validation logic here
        return res
    
   