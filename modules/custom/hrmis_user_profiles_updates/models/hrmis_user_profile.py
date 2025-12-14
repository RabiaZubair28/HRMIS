from odoo import models, fields, api

class HrmisUserProfile(models.Model):
    _name = "hrmis.user.profile"
    _description = "HRMIS User Profile"
    _rec_name = "employee_id"

    employee_id = fields.Many2one(
        'hr.employee', string="Employee", required=True, ondelete="cascade"
    )

    father_name = fields.Char(string="Father's Name")
    cnic = fields.Char(string="CNIC", required=True)
    date_of_birth = fields.Date(string="Date of Birth")
    joining_date = fields.Date(string="Joining Date", required=True)
    gender = fields.Selection([
        ('male', 'Male'),
        ('female', 'Female'),
        ('other', 'Other')
    ], string="Gender", required=True)
    cadre = fields.Char(string="Cadre")
    designation = fields.Char(string="Designation")
    bps = fields.Selection([
        ('17', '17'),
        ('18', '18'),
        ('19', '19'),
        ('20', '20')
    ],string="BPS")
    district_id = fields.Many2one('x_district.master', string="Current Posting District")
    facility_id = fields.Many2one(
    'x_facility.type', string="Current Posting Facility",
    domain="[('district_id','=',district_id)]"
)
    contact_info = fields.Char(string="Contact Info")
    description = fields.Text(string="Additional Notes")
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('cnic_unique', 'unique(cnic)', 'CNIC must be unique!')
    ]

    @api.model_create_multi
    def create(self, vals_list):
        profiles = super().create(vals_list)
        for profile in profiles:
            if profile.employee_id:
                profile.employee_id.hrmis_profile_id = profile.id
        return profiles


    @api.onchange('district_id')
    def _onchange_district(self):
        """Filter facilities based on selected district"""
        if self.district_id:
            return {'domain': {'facility_id': [('district_id', '=', self.district_id.id)]}}
        else:
            return {'domain': {'facility_id': []}}