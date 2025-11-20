from odoo import models, fields, api

class ProductTemplate(models.Model):
    _inherit = "product.template"

    # 🔹 هل المنتج مخصص للتوريد؟
    product_for_supply = fields.Boolean(
        string="Product For Supply ?",
        default=False,
        help="Enable this if the product is allowed to be handled by the supply department."
    )

    custom_supply_field_1 = fields.Selection(
        [('basic', 'Basic'), ('secondary', 'Secondary')],
        string="Supply Type",
        default='secondary',
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
        'custom_supply.unit',
        string="Supply Unit",
        help="Select the unit used for supply (e.g. Carton, Bag, Box, Piece, Kilogram, Unit)"
    )
