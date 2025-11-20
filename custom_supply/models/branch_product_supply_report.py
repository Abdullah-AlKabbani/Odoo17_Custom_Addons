# -*- coding: utf-8 -*-
from odoo import models, fields, tools

class BranchProductSupplyReport(models.Model):
    _name = "custom_supply.branch_product_supply_report"
    _description = "Branch Product Supply Report"
    _auto = False
    _rec_name = "branch_name"

    branch_id = fields.Many2one("custom_supply.branch", string="Branch", readonly=True)
    branch_name = fields.Char(string="Branch Name", readonly=True)

    product_id = fields.Many2one("product.product", string="Product", readonly=True)
    product_name = fields.Char(string="Product Name", readonly=True)
    product_name_str = fields.Char(string="Product Name (Display)", readonly=True)
    full_label = fields.Char(string="Full Label", readonly=True)

    total_qty = fields.Float(string="Total Quantity", readonly=True)

    request_date = fields.Datetime(string="Request Date", readonly=True)
    supply_confirm_date = fields.Datetime(string="Supply Confirm Date", readonly=True)
    warehouse_export_date = fields.Datetime(string="Warehouse Export Date", readonly=True)

    def init(self):
        tools.drop_view_if_exists(self._cr, self._table)
        self._cr.execute(f"""
            CREATE OR REPLACE VIEW {self._table} AS (
                SELECT
                    ROW_NUMBER() OVER () AS id,
                    b.id AS branch_id,
                    b.name AS branch_name,
                    p.id AS product_id,
                    pt.name AS product_name,
                    pt.name->>'en_US' AS product_name_str,
                    (pt.name->>'en_US') AS full_label,
                    COALESCE(SUM(l.supply_qty), 0) AS total_qty,
                    r.request_date AS request_date,
                    r.supply_confirm_date AS supply_confirm_date,
                    r.warehouse_export_date AS warehouse_export_date
                FROM custom_supply_supply_request_line l
                LEFT JOIN custom_supply_supply_request r ON l.request_id = r.id
                LEFT JOIN custom_supply_branch b ON r.branch_id = b.id
                LEFT JOIN product_product p ON l.product_id = p.id
                LEFT JOIN product_template pt ON p.product_tmpl_id = pt.id
                GROUP BY b.id, b.name, p.id, pt.name, r.request_date, r.supply_confirm_date, r.warehouse_export_date
            )
        """)
