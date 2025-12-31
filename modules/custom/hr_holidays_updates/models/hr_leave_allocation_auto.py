from datetime import date as pydate
from datetime import datetime as pydatetime
from datetime import time as pytime

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models


class HrLeaveAllocation(models.Model):
    _inherit = 'hr.leave.allocation'

    @api.model
    def _total_allocated_days(self, employee_id: int, leave_type_id: int):
        groups = self.read_group(
            [
                ('employee_id', '=', employee_id),
                ('holiday_status_id', '=', leave_type_id),
                ('state', '=', 'validate'),
            ],
            ['number_of_days:sum'],
            [],
            lazy=False,
        )
        return (groups[0].get('number_of_days_sum') or 0.0) if groups else 0.0

    @api.model
    def _year_bounds(self, year: int):
        """
        Return year bounds as datetimes (inclusive) to match Odoo allocation checks.
        """
        start_d = pydate(year, 1, 1)
        end_d = pydate(year, 12, 31)
        start = pydatetime.combine(start_d, pytime.min)
        end = pydatetime.combine(end_d, pytime.max.replace(microsecond=0))
        return start, end

    @api.model
    def _month_bounds(self, year: int, month: int):
        """
        Return month bounds as datetimes (inclusive) to match Odoo allocation checks.
        """
        start_d = pydate(year, month, 1)
        end_d = start_d + relativedelta(months=1, days=-1)
        start = pydatetime.combine(start_d, pytime.min)
        end = pydatetime.combine(end_d, pytime.max.replace(microsecond=0))
        return start, end

    @api.model
    def _ytd_allocated_days(self, employee_id: int, leave_type_id: int, year: int):
        start = pydatetime.combine(pydate(year, 1, 1), pytime.min)
        end = pydatetime.combine(pydate(year, 12, 31), pytime.max.replace(microsecond=0))
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
        if joining and joining > end.date():
            return

        # Respect gender restrictions to avoid invalid allocations
        # If leave type is gender-restricted, require a matching (known) employee gender.
        allowed_gender = getattr(leave_type, 'allowed_gender', 'all') or 'all'
        emp_gender = employee.hrmis_gender or employee.gender or False
        if allowed_gender in ('male', 'female') and (not emp_gender or emp_gender != allowed_gender):
            return

        # Only allocate for policy-enabled leave types
        if not leave_type.auto_allocate or not leave_type.max_days_per_month:
            return

        # Avoid duplicates (tolerant to datetime boundary differences)
        next_month_start = start + relativedelta(months=1)
        existing = self.search([
            ('employee_id', '=', employee.id),
            ('holiday_status_id', '=', leave_type.id),
            ('allocation_type', '=', 'regular'),
            ('state', '=', 'validate'),
            ('date_from', '>=', start),
            ('date_from', '<', next_month_start),
        ], limit=1)
        if existing:
            # Fix legacy allocations that were created with date-only bounds
            # (e.g. month end at 00:00:00), which can fail Odoo's coverage checks.
            updates = {}
            if existing.date_from and existing.date_from > start:
                updates['date_from'] = start
            if existing.date_to and existing.date_to < end:
                updates['date_to'] = end
            if updates:
                existing.sudo().write(updates)
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
    def _ensure_yearly_allocation(self, employee, leave_type, year: int):
        """
        Ensure a validated yearly allocation exists for this employee+leave_type+year.
        Intended for Half Pay: 20 days/year, etc.
        """
        start, end = self._year_bounds(year)

        # Don't allocate before employee exists in service (if HRMIS joining date is set)
        joining = employee.hrmis_joining_date
        if joining and joining > end.date():
            return

        # Respect gender restrictions to avoid invalid allocations
        allowed_gender = getattr(leave_type, 'allowed_gender', 'all') or 'all'
        emp_gender = employee.hrmis_gender or employee.gender or False
        if allowed_gender in ('male', 'female') and (not emp_gender or emp_gender != allowed_gender):
            return

        if not leave_type.auto_allocate or not leave_type.max_days_per_year:
            return

        next_year_start = start + relativedelta(years=1)
        existing = self.search([
            ('employee_id', '=', employee.id),
            ('holiday_status_id', '=', leave_type.id),
            ('allocation_type', '=', 'regular'),
            ('state', '=', 'validate'),
            ('date_from', '>=', start),
            ('date_from', '<', next_year_start),
        ], limit=1)
        if existing:
            updates = {}
            if existing.date_from and existing.date_from > start:
                updates['date_from'] = start
            if existing.date_to and existing.date_to < end:
                updates['date_to'] = end
            if updates:
                existing.sudo().write(updates)
            return

        days = float(leave_type.max_days_per_year)
        if days <= 0.0:
            return

        # Apply lifetime cap when max_times_in_service is configured.
        # Example: maternity 90 days/year, max 3 times => max 270 allocated over employment.
        if leave_type.max_times_in_service:
            total_cap = float(leave_type.max_days_per_year) * float(leave_type.max_times_in_service)
            already = self._total_allocated_days(employee.id, leave_type.id)
            remaining = max(0.0, total_cap - already)
            days = min(days, remaining)
            if days <= 0.0:
                return

        alloc = self.sudo().create({
            'name': f"{leave_type.name} ({start.date()} - {end.date()})",
            'employee_id': employee.id,
            'holiday_status_id': leave_type.id,
            'allocation_type': 'regular',
            'date_from': start,
            'date_to': end,
            'number_of_days': days,
            'state': 'confirm',
        })
        alloc.sudo().action_validate()

    @api.model
    def _ensure_one_time_allocation(self, employee, leave_type):
        """
        Ensure a single validated allocation exists for policy leave types that are not
        monthly/yearly accrual (e.g. Maternity/Paternity/LPR).
        """
        if not leave_type.auto_allocate:
            return

        # Skip types that are handled via month/year logic
        if leave_type.max_days_per_month or leave_type.max_days_per_year:
            return

        # Respect gender restrictions to avoid invalid allocations
        allowed_gender = getattr(leave_type, 'allowed_gender', 'all') or 'all'
        emp_gender = employee.hrmis_gender or employee.gender or False
        if allowed_gender in ('male', 'female') and (not emp_gender or emp_gender != allowed_gender):
            return

        existing = self.search([
            ('employee_id', '=', employee.id),
            ('holiday_status_id', '=', leave_type.id),
            ('allocation_type', '=', 'regular'),
            ('state', '=', 'validate'),
        ], limit=1)
        if existing:
            return

        # Allocate total entitlement for the employee's service.
        per_req = float(leave_type.max_days_per_request or 0.0)
        if per_req <= 0.0:
            return
        times = int(leave_type.max_times_in_service or 0)
        total = per_req * (times if times > 0 else 1)

        joining = employee.hrmis_joining_date or fields.Date.today()
        start = pydatetime.combine(pydate(joining.year, joining.month, joining.day), pytime.min)

        alloc = self.sudo().create({
            'name': f"{leave_type.name} (Service Entitlement)",
            'employee_id': employee.id,
            'holiday_status_id': leave_type.id,
            'allocation_type': 'regular',
            'date_from': start,
            # No end date => usable throughout employment
            'date_to': False,
            'number_of_days': total,
            'state': 'confirm',
        })
        alloc.sudo().action_validate()

    @api.model
    def cron_auto_allocate_policy_leaves(self):
        """
        Automatically create validated allocations for leave types with auto_allocate=True.
        Supports:
        - Monthly allocations (e.g. CL 2 days/month)
        - Yearly allocations (e.g. Half Pay 20 days/year)
        - One-time employment entitlements (e.g. Maternity/Paternity/LPR)
        """
        today = fields.Date.today()
        year = today.year

        leave_types = self.env['hr.leave.type'].search([('auto_allocate', '=', True)])
        if not leave_types:
            return

        employees = self.env['hr.employee'].search([('active', '=', True)])
        if not employees:
            return

        # Backfill allocations so balances appear immediately
        for lt in leave_types:
            for emp in employees:
                if lt.max_days_per_month:
                    for month in range(1, today.month + 1):
                        self._ensure_monthly_allocation(emp, lt, year, month)
                elif lt.max_days_per_year:
                    self._ensure_yearly_allocation(emp, lt, year)
                else:
                    self._ensure_one_time_allocation(emp, lt)

