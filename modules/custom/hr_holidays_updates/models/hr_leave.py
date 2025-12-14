from odoo import models, fields, api
from odoo.exceptions import ValidationError

class HrLeave(models.Model):
    _inherit = 'hr.leave'

    hrmis_profile_id = fields.Many2one(
        'hrmis.user.profile',
        string="HRMIS Profile",
        related="employee_id.hrmis_profile_id",
        readonly=True,
    )

    employee_gender = fields.Selection(
        selection=[('male', 'Male'), ('female', 'Female'), ('other', 'Other')],
        string="Employee Gender",
        compute="_compute_employee_gender",
        readonly=True,
    )

    leave_type_allowed_gender = fields.Selection(
        related="holiday_status_id.allowed_gender",
        string="Leave Type Allowed Gender",
        readonly=True,
    )

    @api.depends('employee_id', 'employee_id.hrmis_gender', 'employee_id.gender')
    def _compute_employee_gender(self):
        """
        Prefer HRMIS gender (if available) and fall back to built-in hr.employee gender.
        """
        for leave in self:
            leave.employee_gender = leave.employee_id.hrmis_gender or leave.employee_id.gender or False

    @api.onchange('employee_id', 'holiday_status_id','hrmis_profile_id')
    def _onchange_employee_filter_leave_type(self):
        if not self.employee_id:
            return {'domain': {'holiday_status_id': []}}

        gender = self.employee_gender
        if gender in ('male', 'female'):
            # Treat empty (False) as "All" for legacy leave types.
            domain = [('allowed_gender', 'in', [False, 'all', gender])]
        else:
            # If gender is missing/other, keep only gender-neutral leave types.
            domain = [('allowed_gender', 'in', [False, 'all'])]

        return {'domain': {'holiday_status_id': domain}}

    @api.constrains('employee_id', 'holiday_status_id')
    def _check_leave_type_gender(self):
        for leave in self:
            if not leave.employee_id or not leave.holiday_status_id:
                continue

            allowed = leave.holiday_status_id.allowed_gender or 'all'
            if allowed == 'all':
                continue

            gender = leave.employee_gender
            if not gender or gender != allowed:
                raise ValidationError(
                    "This leave type is restricted by gender. "
                    "Please select a leave type allowed for this employee."
                )
    



