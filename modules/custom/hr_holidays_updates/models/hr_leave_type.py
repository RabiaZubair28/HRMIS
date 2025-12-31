from odoo import models, fields, api


def _num_to_word(n: int) -> str:
    # Keep intentionally small/safe: only what we need for UI labels.
    words = {
        0: "Zero",
        1: "One",
        2: "Two",
        3: "Three",
        4: "Four",
        5: "Five",
        6: "Six",
        7: "Seven",
        8: "Eight",
        9: "Nine",
        10: "Ten",
    }
    return words.get(n, str(n))


def _fmt_days(v: float) -> str:
    try:
        f = float(v or 0.0)
    except Exception:
        return "0"
    return str(int(f)) if f.is_integer() else f"{f:g}"


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

    auto_allocate = fields.Boolean(
        string="Auto Allocate By Policy",
        default=False,
        help="If enabled, the system will create validated allocations automatically (e.g. monthly CL).",
    )

    @api.model
    def ensure_policy_leave_types(self):
        """
        Ensure core policy leave types exist and are configured so auto-allocation works.
        This runs on module upgrade and is safe to run repeatedly.
        """
        policies = [
            # Earned Leave (Full Pay): monthly entitlement with annual cap
            {
                "names": ["Earned Leave (Full Pay)", "Earned Leave With Pay", "Earned Leave"],
                "canonical_name": "Earned Leave (Full Pay)",
                "vals": {
                    "allowed_gender": "all",
                    "requires_allocation": "yes",
                    "max_days_per_month": 4.0,
                    "max_days_per_year": 48.0,
                    "auto_allocate": True,
                },
            },
            # Leave on Half Pay: yearly entitlement
            {
                "names": ["Leave On Half Pay", "Leave on Half Pay", "Half Pay Leave"],
                "canonical_name": "Leave On Half Pay",
                "vals": {
                    "allowed_gender": "all",
                    "requires_allocation": "yes",
                    "max_days_per_year": 20.0,
                    "max_days_per_month": 0.0,
                    "auto_allocate": True,
                },
            },
            # Maternity: per-request cap and times-in-service (allocated as total entitlement)
            {
                "names": ["Maternity Leave", "Maternity"],
                "canonical_name": "Maternity Leave",
                "vals": {
                    "allowed_gender": "female",
                    "requires_allocation": "yes",
                    "max_days_per_request": 90.0,
                    "max_days_per_year": 90.0,
                    # No lifetime cap requested (yearly entitlement).
                    "max_times_in_service": 0,
                    "auto_allocate": True,
                },
            },
            # Paternity
            {
                "names": ["Paternity Leave", "Paternity"],
                "canonical_name": "Paternity Leave",
                "vals": {
                    "allowed_gender": "male",
                    "requires_allocation": "yes",
                    "max_days_per_request": 7.0,
                    "max_days_per_year": 7.0,
                    # No lifetime cap requested (yearly entitlement).
                    "max_times_in_service": 0,
                    "auto_allocate": True,
                },
            },
            # LPR
            {
                "names": [
                    "Leave Preparatory to Retirement (LPR)",
                    "Leave Preparatory to Retirement",
                    "LPR",
                ],
                "canonical_name": "Leave Preparatory to Retirement (LPR)",
                "vals": {
                    "allowed_gender": "all",
                    "requires_allocation": "yes",
                    "max_days_per_request": 365.0,
                    "max_times_in_service": 0,
                    "auto_allocate": True,
                },
            },
        ]

        for pol in policies:
            dom = []
            for i, nm in enumerate(pol["names"]):
                if i:
                    dom = ["|"] + dom
                dom += [("name", "=ilike", nm)]
            leave_types = self.search(dom)
            if leave_types:
                leave_types.write(pol["vals"])
                continue
            # Only create if none exist under any known alias
            vals = {"name": pol["canonical_name"], **pol["vals"]}
            self.create(vals)

    @api.model
    def archive_unwanted_default_leave_types(self):
        """
        Odoo ships some default time off types (e.g. Paid Time Off / Sick / Unpaid).
        If you don't want them in your instance, archive them safely by name.
        """
        # Exact names seen in standard Odoo databases / hr_holidays defaults.
        unwanted_names = [
            "Paid Time Off",
            "Sick Time Off",
            "Unpaid",
            "Compensatory Days",
        ]

        # Archive any matching types (case-insensitive). Don't delete to avoid breaking references.
        for nm in unwanted_names:
            leave_types = self.search([("name", "=ilike", nm)])
            if leave_types:
                leave_types.write({"active": False})

    @api.model
    def ensure_approval_allocated_leave_types(self):
        """
        Ensure these leave types exist so they appear in Odoo Time Off lists.
        They are NOT auto-allocated; balance stays 0/0 until an allocation request
        is approved (hence the label note in name_get()).
        """
        names = [
            "Fitness To Resume Duty",
            "Medical Leave (Long Term)",
            "Medical Leave (Long-term)",
            "Study Leave",
            "Special Leave (Quarantine)",
            "Special Leave - Quarantine",
            "Special Leave (Accident/Injury)",
            "Special Leave (Accident / Injury)",
            "Special Leave Accident / Injuring",
        ]

        base_vals = {
            "active": True,
            "allowed_gender": "all",
            "requires_allocation": "yes",
            "auto_allocate": False,
            "min_service_months": 0,
        }

        for nm in names:
            lt = self.search([("name", "=ilike", nm)], limit=1)
            if lt:
                lt.write(base_vals)
            else:
                self.create({"name": nm, **base_vals})

    @api.model
    def apply_support_document_rules(self):
        """
        Ensure the listed leave types require a supporting document.
        This is safe to run on every module upgrade.
        """
        rules = {
            # User-requested rules
            "Leave Without Pay (EOL)": "Written request would be attached.",
            "Leave Without Pay": "Written request would be attached.",

            "Maternity Leave": "Medical Certificate.",

            "Ex-Pakistan Leave": "Govt. Permission Letter.",

            "Special Leave (Accident/Injury)": "Medical Certificate.",
            "Special Leave (Accident / Injury)": "Medical Certificate.",

            "Study Leave": "Admission Letter / Course Details.",

            "Medical Leave (Long Term)": "Medical Certificate.",

            "Fitness To Resume Duty": "Fitness Certificate.",

            # Keep existing (not mentioned in latest request, but harmless)
            "Special Leave (Quarantine)": "Quarantine order.",
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
            "Casual Leave (CL)": {"max_days_per_month": 2.0, "max_days_per_year": 24.0, "auto_allocate": True},
            "Casual Leave": {"max_days_per_month": 2.0, "max_days_per_year": 24.0, "auto_allocate": True},

            # Earned Leave (Full Pay): 4 days/month, 48 days/year
            "Earned Leave (Full Pay)": {"max_days_per_month": 4.0, "max_days_per_year": 48.0, "auto_allocate": True},
            "Earned Leave With Pay": {"max_days_per_month": 4.0, "max_days_per_year": 48.0, "auto_allocate": True},
            "Earned Leave": {"max_days_per_month": 4.0, "max_days_per_year": 48.0, "auto_allocate": True},

            # Leave on Half Pay: 20 days/year
            "Leave On Half Pay": {"max_days_per_year": 20.0, "auto_allocate": True},
            "Leave on Half Pay": {"max_days_per_year": 20.0, "auto_allocate": True},
            "Half Pay Leave": {"max_days_per_year": 20.0, "auto_allocate": True},

            # Maternity: 90 days per request, max 3 times in service
            "Maternity Leave": {"max_days_per_request": 90.0, "max_days_per_year": 90.0, "max_times_in_service": 0, "auto_allocate": True},
            "Maternity": {"max_days_per_request": 90.0, "max_days_per_year": 90.0, "max_times_in_service": 0, "auto_allocate": True},

            # Paternity: 7 days per request, max 2 times in service
            "Paternity Leave": {"max_days_per_request": 7.0, "max_days_per_year": 7.0, "max_times_in_service": 0, "auto_allocate": True},
            "Paternity": {"max_days_per_request": 7.0, "max_days_per_year": 7.0, "max_times_in_service": 0, "auto_allocate": True},

            # Study: up to 2 years (extendable by 1) -> enforce max 3 years per request
            "Study Leave": {"max_days_per_request": 1095.0},

            # LPR: max 365 days
            "Leave Preparatory to Retirement (LPR)": {"max_days_per_request": 365.0, "auto_allocate": True},
            "LPR": {"max_days_per_request": 365.0, "auto_allocate": True},
            "Leave Preparatory to Retirement": {"max_days_per_request": 365.0, "auto_allocate": True},
        }

        for leave_type_name, vals in rules.items():
            leave_types = self.search([('name', '=ilike', leave_type_name)])
            if not leave_types:
                continue
            leave_types.write(vals)

    @api.model
    def ensure_casual_leave_policy(self):
        """
        Ensure a Casual Leave type exists and matches policy:
        - 2 days/month (auto-allocated monthly)
        - 24 days/year cap
        """
        # Try common naming variants to avoid creating duplicates.
        lt = self.search(
            ['|', ('name', '=ilike', 'Casual Leave'), ('name', '=ilike', 'Casual Leave (CL)')],
            limit=1,
        )
        vals = {
            'name': lt.name if lt else 'Casual Leave',
            'allowed_gender': 'all',
            # Odoo core field (selection): yes/no. Keep CL allocation-based.
            'requires_allocation': 'yes',
            # Policy fields used by our monthly cron + request constraints
            'max_days_per_month': 2.0,
            'max_days_per_year': 24.0,
            'auto_allocate': True,
        }
        if lt:
            lt.write(vals)
        else:
            self.create(vals)

    def name_get(self):
        """
        - In employee balance contexts, Odoo typically shows:
          "Type (X remaining out of Y days)".
          For specific types that are allocated only after allocation approval, replace
          "0 remaining out of 0 days" with "(allocated after allocation request approval)".

        - Outside employee contexts, show policy limits:
          Example: "Casual Leave (2 (Two) days/month, 24 days/year)"
        """
        ctx = dict(self.env.context or {})
        emp_id = ctx.get("employee_id") or ctx.get("default_employee_id")

        def _is_alloc_after_approval(leave_type_name: str) -> bool:
            n = (leave_type_name or "").strip().lower()
            if "fitness to resume duty" in n:
                return True
            if "study leave" in n:
                return True
            if "medical leave" in n and "long" in n:
                return True
            if "special leave" in n and "quarantine" in n:
                return True
            if "special leave" in n and ("accident" in n or "injury" in n or "injuring" in n):
                return True
            return False

        res = []
        for lt in self:
            base = lt.name or ""

            # Employee balance context: mimic Odoo label with remaining/out-of.
            if emp_id:
                label = base
                try:
                    days = lt.with_context(employee_id=emp_id).get_days(emp_id) if hasattr(lt, "get_days") else {}
                    info = days.get(emp_id) if isinstance(days, dict) else None
                    if isinstance(info, dict):
                        remaining = info.get("virtual_remaining_leaves")
                        if remaining is None:
                            remaining = info.get("remaining_leaves", 0.0)
                        total = info.get("max_leaves", 0.0)
                    else:
                        remaining = 0.0
                        total = 0.0
                except Exception:
                    remaining = 0.0
                    total = 0.0

                if _is_alloc_after_approval(base) and float(remaining or 0.0) == 0.0 and float(total or 0.0) == 0.0:
                    label = f"{base} (allocated after allocation request approval)"
                else:
                    label = f"{base} ({_fmt_days(remaining)} remaining out of {_fmt_days(total)} days)"

                res.append((lt.id, label))
                continue

            # Non-employee contexts: show policy limits.
            name = base
            parts = []
            if lt.max_days_per_month:
                m = float(lt.max_days_per_month)
                if m.is_integer():
                    mi = int(m)
                    if mi == 2:
                        parts.append(f"{mi} ({_num_to_word(mi)}) days/month")
                    else:
                        parts.append(f"{mi} days/month")
                else:
                    parts.append(f"{m:g} days/month")
            if lt.max_days_per_year:
                y = float(lt.max_days_per_year)
                if y.is_integer():
                    parts.append(f"{int(y)} days/year")
                else:
                    parts.append(f"{y:g} days/year")
            if parts:
                name = f"{name} ({', '.join(parts)})"
            res.append((lt.id, name))

        return res

    def _check_allocation(self, employee_id, request_date_from, request_date_to):
        # Restore standard Odoo allocation validation.
        return super()._check_allocation(employee_id, request_date_from, request_date_to)
    
   