# -*- coding: utf-8 -*-
from odoo import models, fields, api, tools
from datetime import timedelta


class HighManagerAvgDuration(models.Model):
    _name = "custom_supply.high_manager_report_avg_duration"
    _description = "High Manager - Average Durations (Supply / InWarehouse)"
    _auto = False
    _order = "id"

    id = fields.Integer("ID", readonly=True)

    state = fields.Selection(
        [
            ('Supply', 'Supply'),
            ('InWarehouse', 'InWarehouse')
        ],
        string="State",
        readonly=True
    )

    avg_duration_seconds = fields.Float("Average Duration (seconds)", readonly=True)
    # ===== حقل محسوب لعرضها بشكل مقروء =====
    avg_duration_readable = fields.Char(string="Average Duration (Readable)", compute="_compute_avg_readable", store=False)

    # ===== دالة حساب شكل الوقت المقروء =====
    def _compute_avg_readable(self):
        for rec in self:
            secs = rec.avg_duration_seconds or 0
            secs = int(secs)
            rec.avg_duration_readable = str(timedelta(seconds=secs))

    # ===== إنشاء الـ SQL View =====
    @api.model
    def init(self):
        tools.drop_view_if_exists(self.env.cr, 'custom_supply_high_manager_report_avg_duration')
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW custom_supply_high_manager_report_avg_duration AS
            SELECT
                1 AS id,
                'Supply'::text AS state,
                COALESCE(
                    AVG(EXTRACT(EPOCH FROM (supply_confirm_date - request_date))),
                    0
                )::double precision AS avg_duration_seconds
            FROM custom_supply_supply_request
            WHERE supply_confirm_date IS NOT NULL
              AND request_date IS NOT NULL

            UNION ALL

            SELECT
                2 AS id,
                'InWarehouse'::text AS state,
                COALESCE(
                    AVG(EXTRACT(EPOCH FROM (warehouse_export_date - supply_confirm_date))),
                    0
                )::double precision AS avg_duration_seconds
            FROM custom_supply_supply_request
            WHERE warehouse_export_date IS NOT NULL
              AND supply_confirm_date IS NOT NULL;
        """)
