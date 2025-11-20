# -*- coding: utf-8 -*-
from odoo import models, fields, api, tools


class SupplyVsExportReport(models.Model):
    _name = "custom_supply.supply_vs_export_report"
    _description = "Supply vs Export Quantity Report"
    _auto = False
    _order = "id"

    id = fields.Integer("ID", readonly=True)

    category = fields.Selection([
        ('match', 'Matches'),
        ('discrepancy', 'Discrepancies')
    ], string="Category", readonly=True)

    total_count = fields.Integer("Total Count", readonly=True)

    @api.model
    def init(self):
        tools.drop_view_if_exists(self.env.cr, 'custom_supply_supply_vs_export_report')
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW custom_supply_supply_vs_export_report AS (

                -- Count of Matches
                SELECT
                    1 AS id,
                    'match' AS category,
                    COUNT(*) AS total_count
                FROM custom_supply_supply_request_line
                WHERE export_qty IS NOT NULL
                  AND supply_qty IS NOT NULL
                  AND export_qty = supply_qty

                UNION ALL

                -- Count of Discrepancies
                SELECT
                    2 AS id,
                    'discrepancy' AS category,
                    COUNT(*) AS total_count
                FROM custom_supply_supply_request_line
                WHERE export_qty IS NOT NULL
                  AND supply_qty IS NOT NULL
                  AND export_qty != supply_qty
            );
        """)
