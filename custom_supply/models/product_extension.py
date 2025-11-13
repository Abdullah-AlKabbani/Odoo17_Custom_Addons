from odoo import models, fields, api

class ProductTemplate(models.Model):
    _inherit = "product.template"

    custom_supply_field_1 = fields.Selection(
        [('basic', 'Basic'), ('secondary', 'Secondary')],
        string="Supply Type",
        default='basic',
        help="Define if the product is Basic or Secondary for Supply Requests"
    )

    custom_supply_field_2 = fields.Char(
        string="Additional Info",
        help="Optional field for extra information"
    )

    branch_product_ids = fields.One2many(
        'custom_supply.branch_product',
        'product_id',
        string="Branch Products"
    )

    # 🔹 حقل Many2one للوحدة، مرتبط بالوحدات المعرفة في custom_supply.unit
    supply_unit_id = fields.Many2one(
        'custom_supply.unit',  # هنا كان خطأ سابقًا: 'custom_supply.supply_unit' يجب أن يكون 'custom_supply.unit'
        string="Supply Unit",
        help="Select the unit used for supply (e.g. Carton, Bag, Box, Piece, Kilogram, Unit)"
    )
