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

    fitness_resume_duty_eligible = fields.Boolean(
        string="Eligible for Fitness To Resume Duty",
        compute="_compute_fitness_resume_duty_eligible",
        readonly=True,
    )

    employee_leave_balance_total = fields.Float(
        string="Total Leave Balance (Days)",
        compute="_compute_employee_leave_balances",
        readonly=True,
        help="Approximate total available leave balance across all leave types (validated allocations - validated leaves).",
    )

    employee_earned_leave_balance = fields.Float(
        string="Earned Leave Balance (Days)",
        compute="_compute_employee_leave_balances",
        readonly=True,
        help="Approximate available balance for Earned Leave (validated allocations - validated leaves).",
    )

    @api.depends('employee_id', 'employee_id.hrmis_gender', 'employee_id.gender')
    def _compute_employee_gender(self):
        """
        Prefer HRMIS gender (if available) and fall back to built-in hr.employee gender.
        """
        for leave in self:
            leave.employee_gender = leave.employee_id.hrmis_gender or leave.employee_id.gender or False

    def _is_fitness_resume_duty_eligible(self, employee, ref_date):
        """
        Fitness To Resume Duty is only applicable if the employee "just came back"
        from an approved Maternity or Medical leave.

        Implementation: the most recent approved leave ending before the request
        start date must be a Maternity/Medical leave type.
        """
        if not employee:
            return False

        ref_dt = fields.Datetime.to_datetime(ref_date or fields.Date.today())
        last_leave = self.env['hr.leave'].search([
            ('employee_id', '=', employee.id),
            ('state', '=', 'validate'),
            ('date_to', '<=', ref_dt),
        ], order='date_to desc', limit=1)

        if not last_leave:
            return False

        lt_name = (last_leave.holiday_status_id.name or '').strip().lower()
        return ('maternity' in lt_name) or ('medical' in lt_name)

    @api.depends('employee_id', 'request_date_from')
    def _compute_fitness_resume_duty_eligible(self):
        for leave in self:
            leave.fitness_resume_duty_eligible = self._is_fitness_resume_duty_eligible(
                leave.employee_id,
                leave.request_date_from or fields.Date.today(),
            )

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

    @api.depends('employee_id')
    def _compute_employee_leave_balances(self):
        """
        Compute approximate leave balances from validated allocations and validated leaves.
        This intentionally ignores edge cases (accrual calendars, validity periods) unless your policy needs them.
        """
        employees = self.mapped('employee_id')
        if not employees:
            for leave in self:
                leave.employee_leave_balance_total = 0.0
                leave.employee_earned_leave_balance = 0.0
            return

        # Gather earned leave type ids (name-based to match your setup)
        earned_types = self.env['hr.leave.type'].search([
            '|', '|',
            ('name', '=ilike', 'Earned Leave (Full Pay)'),
            ('name', '=ilike', 'Earned Leave With Pay'),
            ('name', '=ilike', 'Earned Leave'),
        ])
        earned_type_ids = set(earned_types.ids)

        # Allocation sums by employee + leave type
        alloc_groups = self.env['hr.leave.allocation'].read_group(
            [('employee_id', 'in', employees.ids), ('state', '=', 'validate')],
            ['employee_id', 'holiday_status_id', 'number_of_days:sum'],
            ['employee_id', 'holiday_status_id'],
            lazy=False,
        )
        # Leave sums by employee + leave type
        leave_groups = self.env['hr.leave'].read_group(
            [('employee_id', 'in', employees.ids), ('state', '=', 'validate')],
            ['employee_id', 'holiday_status_id', 'number_of_days:sum'],
            ['employee_id', 'holiday_status_id'],
            lazy=False,
        )

        # Build dicts: sums[(emp_id, type_id)] = total_days
        alloc_sum = {}
        for g in alloc_groups:
            emp = g.get('employee_id') and g['employee_id'][0]
            lt = g.get('holiday_status_id') and g['holiday_status_id'][0]
            if emp and lt:
                alloc_sum[(emp, lt)] = g.get('number_of_days_sum') or 0.0

        leave_sum = {}
        for g in leave_groups:
            emp = g.get('employee_id') and g['employee_id'][0]
            lt = g.get('holiday_status_id') and g['holiday_status_id'][0]
            if emp and lt:
                leave_sum[(emp, lt)] = g.get('number_of_days_sum') or 0.0

        # Compute per employee
        total_by_emp = {e.id: 0.0 for e in employees}
        earned_by_emp = {e.id: 0.0 for e in employees}

        # Consider all type keys we saw in either allocations or leaves
        all_keys = set(alloc_sum.keys()) | set(leave_sum.keys())
        for (emp_id, type_id) in all_keys:
            bal = (alloc_sum.get((emp_id, type_id), 0.0) - leave_sum.get((emp_id, type_id), 0.0))
            if bal > 0:
                total_by_emp[emp_id] = total_by_emp.get(emp_id, 0.0) + bal
            if type_id in earned_type_ids:
                earned_by_emp[emp_id] = earned_by_emp.get(emp_id, 0.0) + bal

        for leave in self:
            emp_id = leave.employee_id.id if leave.employee_id else False
            leave.employee_leave_balance_total = total_by_emp.get(emp_id, 0.0) if emp_id else 0.0
            leave.employee_earned_leave_balance = earned_by_emp.get(emp_id, 0.0) if emp_id else 0.0

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

        # Fitness To Resume Duty eligibility: hide unless last approved leave was maternity/medical
        fitness_type = self.env['hr.leave.type'].search([('name', '=ilike', 'Fitness To Resume Duty')], limit=1)
        if fitness_type and not self.fitness_resume_duty_eligible:
            domain += [('id', '!=', fitness_type.id)]

        # Ex-Pakistan: only if employee has any leave balance
        ex_pk = self.env['hr.leave.type'].search([('name', '=ilike', 'Ex-Pakistan Leave')], limit=1)
        if ex_pk and (self.employee_leave_balance_total or 0.0) <= 0.0:
            domain += [('id', '!=', ex_pk.id)]

        # LPR: only if employee has earned leave balance
        lpr = self.env['hr.leave.type'].search([
            '|',
            ('name', '=ilike', 'Leave Preparatory to Retirement (LPR)'),
            ('name', '=ilike', 'LPR'),
        ], limit=1)
        if lpr and (self.employee_earned_leave_balance or 0.0) <= 0.0:
            domain += [('id', '!=', lpr.id)]

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

    @api.constrains('employee_id', 'holiday_status_id', 'request_date_from', 'state')
    def _check_fitness_resume_duty_prereq(self):
        for leave in self:
            if not leave.employee_id or not leave.holiday_status_id:
                continue
            if leave.state in ('cancel', 'refuse'):
                continue

            if (leave.holiday_status_id.name or '').strip().lower() != 'fitness to resume duty':
                continue

            ref_date = leave.request_date_from or fields.Date.today()
            if not leave._is_fitness_resume_duty_eligible(leave.employee_id, ref_date):
                raise ValidationError(
                    "Fitness To Resume Duty is only applicable if the employee has just returned "
                    "from an approved Maternity or Medical leave."
                )

    @api.constrains('employee_id', 'holiday_status_id', 'state')
    def _check_leave_balance_prereqs(self):
        """
        - Ex-Pakistan Leave requires employee to have some leave balance overall.
        - LPR requires employee to have Earned Leave balance.
        """
        for leave in self:
            if not leave.employee_id or not leave.holiday_status_id:
                continue
            if leave.state in ('cancel', 'refuse'):
                continue

            lt_name = (leave.holiday_status_id.name or '').strip().lower()
            if lt_name == 'ex-pakistan leave' and (leave.employee_leave_balance_total or 0.0) <= 0.0:
                raise ValidationError(
                    "Ex-Pakistan Leave is only applicable to employees who have a leave balance."
                )

            if lt_name in ('leave preparatory to retirement (lpr)', 'lpr') and (leave.employee_earned_leave_balance or 0.0) <= 0.0:
                raise ValidationError(
                    "LPR is only applicable to employees who have an Earned Leave balance."
                )

    def _vals_include_any_attachment(self, vals):
        """
        Detect attachments being added in the same create/write call.
        This avoids false negatives where constraints run before attachments are linked.
        """
        if not vals:
            return False

        # Explicit attachment fields
        for key in ('supported_attachment_ids', 'attachment_ids', 'message_main_attachment_id'):
            if key not in vals:
                continue
            v = vals.get(key)
            if key == 'message_main_attachment_id':
                return bool(v)

            # m2m/o2m command list
            if isinstance(v, (list, tuple)):
                for cmd in v:
                    if not isinstance(cmd, (list, tuple)) or not cmd:
                        continue
                    op = cmd[0]
                    # (6, 0, [ids]) set
                    if op == 6 and len(cmd) >= 3 and cmd[2]:
                        return True
                    # (4, id) link
                    if op == 4 and len(cmd) >= 2 and cmd[1]:
                        return True
                    # (0, 0, values) create
                    if op == 0:
                        return True
            elif v:
                return True

        return False

    def _enforce_supporting_documents_required(self, incoming_vals=None):
        """
        Enforce supporting documents for leave types that require them.
        Implemented as a post create/write check to avoid timing issues with
        many2many_binary uploads (common with PDFs).
        """
        # TEMPORARILY DISABLED (per request): supporting documents enforcement
        # to allow testing of other eligibility rules without being blocked.
        return
        for leave in self:
            if not leave.holiday_status_id:
                continue
            if leave.state in ('cancel', 'refuse'):
                continue
            if not leave.holiday_status_id.support_document:
                continue

            # If the attachment is being added in the same transaction, accept it.
            if self._vals_include_any_attachment(incoming_vals or {}):
                continue

            # Otherwise, verify there is at least one persisted attachment linked to this leave.
            count = self.env['ir.attachment'].sudo().search_count([
                ('res_model', '=', 'hr.leave'),
                ('res_id', '=', leave.id),
            ])
            if count <= 0:
                raise ValidationError(
                    "A supporting document is required for this Time Off Type. "
                    "Please attach the required document before submitting."
                )

    @api.model_create_multi
    def create(self, vals_list):
        leaves = super().create(vals_list)
        for leave, vals in zip(leaves, vals_list):
            leave._enforce_supporting_documents_required(vals)
        return leaves

    def write(self, vals):
        res = super().write(vals)
        self._enforce_supporting_documents_required(vals)
        return res

    def _period_bounds(self, ref_date, period):
        ref_date = fields.Date.to_date(ref_date or fields.Date.today())
        if period == 'month':
            start = ref_date.replace(day=1)
            end = start + relativedelta(months=1, days=-1)
            return start, end
        if period == 'year':
            start = ref_date.replace(month=1, day=1)
            end = ref_date.replace(month=12, day=31)
            return start, end
        return None, None

    @api.constrains('employee_id', 'holiday_status_id', 'request_date_from', 'number_of_days', 'state')
    def _check_max_duration_rules(self):
        for leave in self:
            if not leave.employee_id or not leave.holiday_status_id:
                continue
            if leave.state in ('cancel', 'refuse'):
                continue

            lt = leave.holiday_status_id
            days = leave.number_of_days or 0.0
            ref = leave.request_date_from or fields.Date.today()

            # Per-request maximum
            if lt.max_days_per_request and days > lt.max_days_per_request:
                raise ValidationError(
                    f"Maximum duration for this Time Off Type is {lt.max_days_per_request} day(s) per request."
                )

            # Times in service
            if lt.max_times_in_service:
                taken_count = self.search_count([
                    ('employee_id', '=', leave.employee_id.id),
                    ('holiday_status_id', '=', lt.id),
                    ('state', 'not in', ('cancel', 'refuse')),
                    ('id', '!=', leave.id),
                ]) + 1
                if taken_count > lt.max_times_in_service:
                    raise ValidationError(
                        f"This Time Off Type can be taken at most {lt.max_times_in_service} time(s) in service."
                    )

            # Per-month maximum (based on request start month)
            if lt.max_days_per_month:
                start, end = leave._period_bounds(ref, 'month')
                used = sum(self.search([
                    ('employee_id', '=', leave.employee_id.id),
                    ('holiday_status_id', '=', lt.id),
                    ('state', 'not in', ('cancel', 'refuse')),
                    ('id', '!=', leave.id),
                    ('request_date_from', '>=', start),
                    ('request_date_from', '<=', end),
                ]).mapped('number_of_days')) or 0.0
                if used + days > lt.max_days_per_month:
                    raise ValidationError(
                        f"Maximum duration for this Time Off Type is {lt.max_days_per_month} day(s) per month."
                    )

            # Per-year maximum (based on request start year)
            if lt.max_days_per_year:
                start, end = leave._period_bounds(ref, 'year')
                used = sum(self.search([
                    ('employee_id', '=', leave.employee_id.id),
                    ('holiday_status_id', '=', lt.id),
                    ('state', 'not in', ('cancel', 'refuse')),
                    ('id', '!=', leave.id),
                    ('request_date_from', '>=', start),
                    ('request_date_from', '<=', end),
                ]).mapped('number_of_days')) or 0.0
                if used + days > lt.max_days_per_year:
                    raise ValidationError(
                        f"Maximum duration for this Time Off Type is {lt.max_days_per_year} day(s) per year."
                    )
    



