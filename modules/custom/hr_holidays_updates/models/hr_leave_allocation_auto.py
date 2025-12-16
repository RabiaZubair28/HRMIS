from datetime import date as pydate

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models


class HrLeaveAllocation(models.Model):
    _inherit = 'hr.leave.allocation'

    @api.model
    def _month_bounds(self, year: int, month: int):
        start = pydate(year, month, 1)
        end = start + relativedelta(months=1, days=-1)
        return start, end

    @api.model
    def _ytd_allocated_days(self, employee_id: int, leave_type_id: int, year: int):
        start = pydate(year, 1, 1)
        end = pydate(year, 12, 31)
        groups = self.read_group(
            [
                ('employee_id', '=', employee_id),
                ('holiday_status_id', '=', leave_type_id),
                ('state', '=', 'validate'),
                ('date_from', '>=', start),
                ('date_from', '<=', end),
            ],
            ['number_of_days:sum'],
            [],
            lazy=False,
        )
        return (groups[0].get('number_of_days_sum') or 0.0) if groups else 0.0

    @api.model
    def _ensure_monthly_allocation(self, employee, leave_type, year: int, month: int):
        start, end = self._month_bounds(year, month)

        # Don't allocate before employee exists in service (if HRMIS joining date is set)
        joining = employee.hrmis_joining_date
        if joining and joining > end:
            return

        # Only allocate for policy-enabled leave types
        if not leave_type.auto_allocate or not leave_type.max_days_per_month:
            return

        # Avoid duplicates
        exists = self.search_count([
            ('employee_id', '=', employee.id),
            ('holiday_status_id', '=', leave_type.id),
            ('allocation_type', '=', 'regular'),
            ('date_from', '=', start),
            ('date_to', '=', end),
            ('state', '=', 'validate'),
        ]) > 0
        if exists:
            return

        # Apply annual cap if configured
        days = float(leave_type.max_days_per_month)
        if leave_type.max_days_per_year:
            ytd = self._ytd_allocated_days(employee.id, leave_type.id, year)
            remaining = max(0.0, float(leave_type.max_days_per_year) - ytd)
            days = min(days, remaining)
            if days <= 0.0:
                return

        alloc = self.sudo().create({
            'name': f"{leave_type.name} ({start} - {end})",
            'employee_id': employee.id,
            'holiday_status_id': leave_type.id,
            'allocation_type': 'regular',
            'date_from': start,
            'date_to': end,
            'number_of_days': days,
            'state': 'confirm',
        })
        # Validate directly (no approval workflow needed)
        alloc.sudo().action_validate()

    @api.model
    def cron_auto_allocate_policy_leaves(self):
        """
        Automatically create validated allocations for leave types with auto_allocate=True.
        Intended for CL: 2 days/month with monthly validity, capped at 24/year.
        """
        today = fields.Date.today()
        year = today.year

        leave_types = self.env['hr.leave.type'].search([('auto_allocate', '=', True)])
        if not leave_types:
            return

        employees = self.env['hr.employee'].search([('active', '=', True)])
        if not employees:
            return

        # Backfill allocations from Jan to current month (so balances appear immediately)
        for lt in leave_types:
            for month in range(1, today.month + 1):
                for emp in employees:
                    self._ensure_monthly_allocation(emp, lt, year, month)

