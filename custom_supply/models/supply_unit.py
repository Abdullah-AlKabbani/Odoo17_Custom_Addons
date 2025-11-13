from odoo import models, fields

class SupplyUnit(models.Model):
    _name = "custom_supply.unit"
    _description = "Supply Unit"

    name = fields.Char(string="Unit Name", required=True)

    _sql_constraints = [
        ('unique_unit_name', 'unique(name)', 'This supply unit name already exists.')
    ]
