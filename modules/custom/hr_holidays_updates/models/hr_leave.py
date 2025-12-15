from odoo import models, fields, api
from odoo.exceptions import ValidationError
from dateutil.relativedelta import relativedelta

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

    support_document_note = fields.Char(
        related="holiday_status_id.support_document_note",
        string="Supporting Document Requirement",
        readonly=True,
    )

    employee_service_months = fields.Integer(
        string="Service (Months)",
        compute="_compute_employee_service_months",
        readonly=True,
    )

    @api.depends('employee_id', 'employee_id.hrmis_gender', 'employee_id.gender')
    def _compute_employee_gender(self):
        """
        Prefer HRMIS gender (if available) and fall back to built-in hr.employee gender.
        """
        for leave in self:
            leave.employee_gender = leave.employee_id.hrmis_gender or leave.employee_id.gender or False

    @api.depends('employee_id', 'employee_id.hrmis_joining_date', 'request_date_from')
    def _compute_employee_service_months(self):
        for leave in self:
            # Use HRMIS joining date (available via hrmis_user_profiles_updates)
            joining_date = leave.employee_id.hrmis_joining_date
            ref_date = leave.request_date_from or fields.Date.today()
            if not joining_date or not ref_date:
                leave.employee_service_months = 0
                continue
            if ref_date < joining_date:
                leave.employee_service_months = 0
                continue
            delta = relativedelta(ref_date, joining_date)
            leave.employee_service_months = delta.years * 12 + delta.months

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

        # Service eligibility: allow types with no minimum, or min <= employee months
        months = self.employee_service_months
        domain += ['|', ('min_service_months', '=', 0), ('min_service_months', '<=', months)]

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

    @api.constrains('employee_id', 'holiday_status_id', 'request_date_from')
    def _check_leave_type_service_eligibility(self):
        for leave in self:
            if not leave.employee_id or not leave.holiday_status_id:
                continue
            required = leave.holiday_status_id.min_service_months or 0
            if required <= 0:
                continue
            if leave.employee_service_months < required:
                raise ValidationError(
                    f"This Time Off Type requires at least {required} months of service. "
                    "This employee is not eligible yet."
                )

    @api.constrains('holiday_status_id', 'attachment_ids', 'state')
    def _check_supporting_documents_required(self):
        """
        Enforce supporting documents for leave types that require them.
        """
        for leave in self:
            if not leave.holiday_status_id:
                continue
            # Only enforce for active workflow states (avoid blocking cancelled/refused history edits)
            if leave.state in ('cancel', 'refuse'):
                continue
            if not leave.holiday_status_id.support_document:
                continue
            # Be permissive in where we count attachments from:
            # - hr.leave's supporting widget (supported_attachment_ids)
            # - hr.leave's attachment_ids
            # - chatter/main attachments
            # - any ir.attachment whose res_id matches (some setups don’t set res_model consistently)
            has_attachment = bool(leave.supported_attachment_ids) or bool(leave.attachment_ids) \
                or bool(leave.message_main_attachment_id) or bool(getattr(leave, 'message_attachment_count', 0))

            if not has_attachment and leave.id:
                any_res_id_match = self.env['ir.attachment'].sudo().search_count([
                    ('res_id', '=', leave.id),
                ])
                has_attachment = any_res_id_match > 0

            if not has_attachment:
                raise ValidationError(
                    "A supporting document is required for this Time Off Type. "
                    "Please attach the required document before submitting."
                )
    



