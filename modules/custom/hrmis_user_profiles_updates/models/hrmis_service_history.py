from odoo import models, fields

class HrmisServiceHistory(models.Model):
    _name = "hrmis.service.history"
    _description = "Service History"
    _rec_name = "employee_id"
    _order = "from_date ASC"

    employee_id = fields.Many2one('hr.employee', string="Employee", required=True, ondelete="cascade")

    facility_name = fields.Char(string="Facility Name")
    facility_type = fields.Char(string="Facility Type")
    district = fields.Char(string="District")

    from_date = fields.Date(string="From Date")
    to_date = fields.Date(string="To Date")
    commission_date = fields.Date(string="Commission Date")
