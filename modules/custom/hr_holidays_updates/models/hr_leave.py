from odoo import models, fields, api
from odoo.exceptions import ValidationError

class HrLeave(models.Model):
    _inherit = 'hr.leave'

    hrmis_profile_id = fields.Many2one('hrmis.user.profile', string="HRMIS Profile")
    employee_gender = fields.Many2one('hrmis.user.profile', string="Gender")

    @api.onchange('employee_id', 'holiday_status_id','hrmis_profile_id')
    def _onchange_employee_filter_leave_type(self):
        if not self.employee_id:
            return {'domain': {'holiday_status_id': []}}

        # Get employee HRMIS profile
        profile = self.hrmis_profile_id
        if not profile:
            return

        gender = profile.gender

        if gender in ('male', 'female','Female','Male'):
            domain = [('allowed_gender', '=', 'male')]
        else:
            domain = [('allowed_gender', '=', 'all')]

        return {'domain': {'holiday_status_id': domain}}
    



