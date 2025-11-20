# -*- coding: utf-8 -*-
from odoo import models, fields, tools

class BranchProductMonthlyReport(models.Model):
    _name = "custom_supply.branch_product_monthly_report"
    _description = "Branch Product Monthly Detailed Report"
    _auto = False

    branch_id = fields.Many2one("custom_supply.branch", string="Branch", readonly=True)
    branch_name = fields.Char(string="Branch Name", readonly=True)

    product_id = fields.Many2one("product.product", string="Product", readonly=True)
    product_name = fields.Char(string="Product Name", readonly=True)

    month = fields.Date(string="Month", readonly=True)
    full_label = fields.Char(string="Full Label", readonly=True)
    total_qty = fields.Float(string="Total Quantity", readonly=True)

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
                    date_trunc('month', r.request_date)::date AS month,
                    COALESCE(SUM(l.supply_qty),0) AS total_qty
                FROM custom_supply_supply_request_line l
                LEFT JOIN custom_supply_supply_request r ON l.request_id = r.id
                LEFT JOIN custom_supply_branch b ON r.branch_id = b.id
                LEFT JOIN product_product p ON l.product_id = p.id
                LEFT JOIN product_template pt ON p.product_tmpl_id = pt.id
                GROUP BY b.id, b.name, p.id, pt.name, date_trunc('month', r.request_date)
                ORDER BY date_trunc('month', r.request_date) DESC, p.id
            )
        """)

class BranchMonthlyRequestCount(models.Model):
    _name = "custom_supply.branch_monthly_request_count"
    _description = "Branch Monthly Supply Request Count Report"
    _auto = False

    branch_id = fields.Many2one("custom_supply.branch", string="Branch", readonly=True)
    branch_name = fields.Char(string="Branch Name", readonly=True)
    month = fields.Char(string="Month", readonly=True)  # صيغة YYYY-MM
    request_count = fields.Integer(string="Number of Requests", readonly=True)

    def init(self):
        tools.drop_view_if_exists(self._cr, self._table)
        self._cr.execute(f"""
            CREATE OR REPLACE VIEW {self._table} AS (
                SELECT
                    ROW_NUMBER() OVER () AS id,
                    b.id AS branch_id,
                    b.name AS branch_name,
                    TO_CHAR(r.request_date, 'YYYY-MM') AS month,
                    COUNT(r.id) AS request_count
                FROM custom_supply_supply_request r
                LEFT JOIN custom_supply_branch b ON r.branch_id = b.id
                GROUP BY b.id, b.name, TO_CHAR(r.request_date, 'YYYY-MM')
                ORDER BY b.id, month
            )
        """)
