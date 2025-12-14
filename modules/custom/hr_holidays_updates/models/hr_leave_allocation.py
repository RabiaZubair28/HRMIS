from odoo import models, fields, api
from odoo.exceptions import ValidationError


class HrLeaveAllocation(models.Model):
    _inherit = 'hr.leave.allocation'

    employee_gender = fields.Selection(
        selection=[('male', 'Male'), ('female', 'Female'), ('other', 'Other')],
        string="Employee Gender",
        compute="_compute_employee_gender",
        readonly=True,
    )

    @api.depends('employee_id', 'employee_id.hrmis_gender', 'employee_id.gender')
    def _compute_employee_gender(self):
        for alloc in self:
            alloc.employee_gender = alloc.employee_id.hrmis_gender or alloc.employee_id.gender or False

    @api.onchange('employee_id')
    def _onchange_employee_filter_leave_type(self):
        """
        Filter Time Off Types by employee gender on allocations as well
        (e.g. maternity for female only, paternity for male only).
        """
        if not self.employee_id:
            return {'domain': {'holiday_status_id': []}}

        gender = self.employee_gender
        if gender in ('male', 'female'):
            # Treat empty (False) as "All" for legacy leave types.
            domain = [('allowed_gender', 'in', [False, 'all', gender])]
        else:
            domain = [('allowed_gender', 'in', [False, 'all'])]

        return {'domain': {'holiday_status_id': domain}}

    @api.constrains('employee_id', 'holiday_status_id')
    def _check_leave_type_gender(self):
        for alloc in self:
            if not alloc.employee_id or not alloc.holiday_status_id:
                continue

            allowed = alloc.holiday_status_id.allowed_gender or 'all'
            if allowed == 'all':
                continue

            gender = alloc.employee_gender
            if not gender or gender != allowed:
                raise ValidationError(
                    "This time off type is restricted by gender. "
                    "Please select a type allowed for this employee."
                )

