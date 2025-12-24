# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date

from odoo import http
from odoo.http import request


def _safe_int(v, default=None):
    try:
        return int(v)
    except Exception:
        return default


def _current_employee():
    """Best-effort mapping from logged-in user -> hr.employee."""
    return (
        request.env["hr.employee"]
        .sudo()
        .search([("user_id", "=", request.env.user.id)], limit=1)
    )


class HrmisLeaveFrontendController(http.Controller):
    # -------------------------------------------------------------------------
    # Odoo Time Off default URLs (override to render the custom UI)
    # -------------------------------------------------------------------------
    @http.route(
        ["/odoo/time-off-overview"], type="http", auth="user", website=True
    )
    def odoo_time_off_overview(self, **kw):
        # Render the same HRMIS "Services" dashboard at the Odoo URL.
        return request.render(
            "hr_holidays_updates.hrmis_services",
            {
                "page_title": "Services",
                "active_menu": "services",
            },
        )

    @http.route(["/odoo/my-time-off"], type="http", auth="user", website=True)
    def odoo_my_time_off(self, **kw):
        emp = _current_employee()
        if not emp:
            return request.render(
                "hr_holidays_updates.hrmis_services",
                {
                    "page_title": "My Time Off",
                    "active_menu": "services",
                },
            )
        # Default to history tab (matches "My Time Off")
        return self.hrmis_leave_form(emp.id, tab="history", **kw)

    @http.route(
        ["/odoo/my-time-off/new"], type="http", auth="user", website=True
    )
    def odoo_my_time_off_new(self, **kw):
        emp = _current_employee()
        if not emp:
            return request.redirect("/odoo/my-time-off")
        # Default to new request tab (matches "New Time Off")
        return self.hrmis_leave_form(emp.id, tab="new", **kw)

    @http.route(["/hrmis", "/hrmis/"], type="http", auth="user", website=True)
    def hrmis_root(self, **kw):
        return request.redirect("/hrmis/services")

    @http.route(["/hrmis/services"], type="http", auth="user", website=True)
    def hrmis_services(self, **kw):
        return request.render(
            "hr_holidays_updates.hrmis_services",
            {
                "page_title": "Services",
                "active_menu": "services",
            },
        )

    @http.route(["/hrmis/staff"], type="http", auth="user", website=True)
    def hrmis_staff_search(self, **kw):
        search_by = (kw.get("search_by") or "designation").strip()
        q = (kw.get("q") or "").strip()

        employees = request.env["hr.employee"].sudo().browse([])
        if q:
            if search_by == "cnic":
                domain = [("hrmis_cnic", "ilike", q)]
            elif search_by == "designation":
                domain = [("hrmis_designation", "ilike", q)]
            elif search_by == "district":
                domain = [("hrmis_district_id.name", "ilike", q)]
            elif search_by == "facility":
                domain = [("hrmis_facility_id.name", "ilike", q)]
            else:
                domain = ["|", ("name", "ilike", q), ("hrmis_designation", "ilike", q)]

            employees = request.env["hr.employee"].sudo().search(domain, limit=50)

        return request.render(
            "hr_holidays_updates.hrmis_staff_search",
            {
                "page_title": "Search staff",
                "active_menu": "staff",
                "search_by": search_by,
                "q": q,
                "employees": employees,
            },
        )

    @http.route(
        ["/hrmis/staff/<int:employee_id>"], type="http", auth="user", website=True
    )
    def hrmis_staff_profile(self, employee_id: int, **kw):
        employee = request.env["hr.employee"].sudo().browse(employee_id).exists()
        if not employee:
            return request.not_found()

        return request.render(
            "hr_holidays_updates.hrmis_staff_profile",
            {
                "page_title": "User profile",
                "active_menu": "staff",
                "employee": employee,
            },
        )

    @http.route(
        ["/hrmis/staff/<int:employee_id>/services"],
        type="http",
        auth="user",
        website=True,
    )
    def hrmis_staff_services(self, employee_id: int, **kw):
        employee = request.env["hr.employee"].sudo().browse(employee_id).exists()
        if not employee:
            return request.not_found()

        return request.render(
            "hr_holidays_updates.hrmis_staff_services",
            {
                "page_title": "Services",
                "active_menu": "staff",
                "employee": employee,
            },
        )

    @http.route(
        ["/hrmis/staff/<int:employee_id>/leave"],
        type="http",
        auth="user",
        website=True,
    )
    def hrmis_leave_form(self, employee_id: int, tab: str = "new", **kw):
        employee = request.env["hr.employee"].sudo().browse(employee_id).exists()
        if not employee:
            return request.not_found()

        leave_types = request.env["hr.leave.type"].sudo().search(
            [("requires_allocation", "=", "no")], order="name asc"
        )
        alloc_types = request.env["hr.leave.type"].sudo().search(
            [("requires_allocation", "!=", "no")], order="name asc"
        )
        leave_types |= alloc_types

        history = request.env["hr.leave"].sudo().search(
            [("employee_id", "=", employee.id)],
            order="request_date_from desc, id desc",
            limit=20,
        )

        error = kw.get("error")
        success = kw.get("success")
        return request.render(
            "hr_holidays_updates.hrmis_leave_form",
            {
                "page_title": "Leave requests",
                "active_menu": "services",
                "employee": employee,
                "tab": tab if tab in ("new", "history") else "new",
                "leave_types": leave_types,
                "history": history,
                "error": error,
                "success": success,
                "today": date.today(),
            },
        )

    @http.route(
        ["/hrmis/staff/<int:employee_id>/leave/submit"],
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    def hrmis_leave_submit(self, employee_id: int, **post):
        employee = request.env["hr.employee"].sudo().browse(employee_id).exists()
        if not employee:
            return request.not_found()

        dt_from = (post.get("date_from") or "").strip()
        dt_to = (post.get("date_to") or "").strip()
        leave_type_id = _safe_int(post.get("leave_type_id"))
        remarks = (post.get("remarks") or "").strip()

        if not dt_from or not dt_to or not leave_type_id or not remarks:
            return request.redirect(
                f"/hrmis/staff/{employee.id}/leave?tab=new&error=Please+fill+all+required+fields"
            )

        try:
            vals = {
                "employee_id": employee.id,
                "holiday_status_id": leave_type_id,
                "request_date_from": dt_from,
                "request_date_to": dt_to,
                "name": remarks,
            }
            leave = request.env["hr.leave"].with_user(request.env.user).create(vals)
            if hasattr(leave, "action_confirm"):
                leave.action_confirm()
        except Exception:
            return request.redirect(
                f"/hrmis/staff/{employee.id}/leave?tab=new&error=Could+not+submit+leave+request"
            )

        return request.redirect(
            f"/hrmis/staff/{employee.id}/leave?tab=history&success=Leave+request+submitted"
        )

    @http.route(["/hrmis/leave/requests"], type="http", auth="user", website=True)
    def hrmis_leave_requests(self, **kw):
        uid = request.env.user.id
        pending = (
            request.env["hr.leave"]
            .sudo()
            .search([("state", "=", "confirm"), ("validation_status_ids.user_id", "=", uid)])
        )
        return request.render(
            "hr_holidays_updates.hrmis_leave_requests",
            {
                "page_title": "Leave requests",
                "active_menu": "leave_requests",
                "leaves": pending,
            },
        )

    @http.route(
        ["/hrmis/leave/<int:leave_id>"], type="http", auth="user", website=True
    )
    def hrmis_leave_view(self, leave_id: int, **kw):
        leave = request.env["hr.leave"].sudo().browse(leave_id).exists()
        if not leave:
            return request.not_found()
        return request.render(
            "hr_holidays_updates.hrmis_leave_view",
            {
                "page_title": "Leave request",
                "active_menu": "leave_requests",
                "leave": leave,
            },
        )

    @http.route(
        ["/hrmis/leave/<int:leave_id>/forward"],
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    def hrmis_leave_forward(self, leave_id: int, **post):
        leave = request.env["hr.leave"].sudo().browse(leave_id).exists()
        if not leave:
            return request.not_found()
        try:
            leave.with_user(request.env.user).action_approve()
        except Exception:
            return request.redirect("/hrmis/leave/requests?error=forward_failed")
        return request.redirect("/hrmis/leave/requests?success=forwarded")

