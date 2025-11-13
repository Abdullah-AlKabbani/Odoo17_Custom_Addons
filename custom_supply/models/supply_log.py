from odoo import models, fields

class SupplyLog(models.Model):
    _name = "custom_supply.supply_log"
    _description = "Supply Log"

    name = fields.Char(string="Description", required=True)
    date = fields.Datetime(string="Date", default=fields.Datetime.now)
    user_id = fields.Many2one("res.users", string="User")
    action_type = fields.Selection([
        ('create', 'Created'),
        ('update', 'Updated'),
        ('delete', 'Deleted'),
    ], string="Action Type")
