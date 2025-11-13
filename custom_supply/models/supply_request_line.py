# -*- coding: utf-8 -*-
import traceback

from odoo import models, fields, api
from odoo.exceptions import UserError
import logging

class SupplyRequestLine(models.Model):
    _name = "custom_supply.supply_request_line"
    _description = "Supply Request Line"

    request_id = fields.Many2one('custom_supply.supply_request', string="Request", ondelete='cascade')
    product_id = fields.Many2one('product.product', string="Product", required=True)
    unit_name = fields.Char(
        string="Unit",
        compute="_compute_unit_name",
        store=False,
        readonly=True
    )

    current_qty = fields.Float(
        string="Current Quantity",
        required=True,
        default=0.0
    )
    suggested_qty = fields.Float(
        string="Suggested Quantity",
        compute="_compute_suggested_qty",
        store=True
    )
    requested_qty = fields.Float(
        string="Requested Quantity",
        required=True,
        default=0.0
    )
    note = fields.Text(string="Note / Reason")
    branch_product_id = fields.Many2one('custom_supply.branch_product', string="Branch Product Link")

    # ================================
    # Supply Manager fields
    # ================================
    supply_qty = fields.Float(string="Supply Quantity", help="Quantity approved by Supply Manager")
    supply_note = fields.Text(string="Supply Note", help="Note / reason from Supply Manager")

    # ================================
    # Warehouse Employee fields
    # ================================
    export_qty = fields.Float(string="Export Quantity", help="Quantity actually exported by Warehouse")
    warehouse_note = fields.Text(string="Warehouse Note", help="Note / reason from Warehouse")

    # ============================
    # Display Name Product
    # ============================
    @api.depends('product_id')
    def _compute_unit_name(self):
        """يحسب اسم الوحدة بناءً على المنتج المختار"""
        for rec in self:
            if rec.product_id and rec.product_id.product_tmpl_id.supply_unit_id:
                rec.unit_name = rec.product_id.product_tmpl_id.supply_unit_id.name
            else:
                rec.unit_name = ''

    # ================================
    # COMPUTE suggested_qty
    # ================================
    @api.depends('product_id', 'current_qty', 'request_id.branch_id')
    def _compute_suggested_qty(self):
        for line in self:
            if not line.product_id or not line.request_id or not line.request_id.branch_id:
                line.suggested_qty = 0.0
                continue
            branch_product = self.env['custom_supply.branch_product'].search([
                ('branch_id', '=', line.request_id.branch_id.id),
                ('product_id', '=', line.product_id.id)
            ], limit=1)
            if branch_product:
                line.suggested_qty = max(0.0, (branch_product.max_quantity or 0.0) - (line.current_qty or 0.0))
            else:
                line.suggested_qty = 0.0

    # ================================
    # CREATE — منع إضافة أسطر غير مصرح بها
    # ================================
    @api.model
    def create(self, vals):
        request = self.env['custom_supply.supply_request'].browse(vals.get('request_id'))

        if request and request.status not in ('InBranch', 'Supply'):
            raise UserError("You cannot add new lines when the request is not in 'InBranch' or 'Supply' status.")

        user = self.env.user
        if request:
            if request.status == 'InBranch' and not user.has_group('custom_supply.group_branch_employee'):
                raise UserError("Only Branch Employee can add lines in 'InBranch' status.")
            if request.status == 'Supply' and not user.has_group('custom_supply.group_supply_manager'):
                raise UserError("Only Supply Manager can add lines in 'Supply' status.")

        # تحقق من branch_product_id
        product_id = vals.get('product_id')
        branch_product_id = vals.get('branch_product_id')
        if not branch_product_id and request:
            branch_id = request.branch_id
            branch_product = self.env['custom_supply.branch_product'].search([
                ('branch_id', '=', branch_id.id),
                ('product_id', '=', product_id)
            ], limit=1)
            if branch_product:
                vals['branch_product_id'] = branch_product.id
            else:
                raise UserError(f"Cannot add product not defined in branch '{branch_id.name}'")

        # تعبئة current_qty إذا لم يُرسل
        if not vals.get('current_qty') and request and product_id:
            bp = self.env['custom_supply.branch_product'].search([
                ('branch_id', '=', request.branch_id.id),
                ('product_id', '=', product_id)
            ], limit=1)
            if bp:
                vals['current_qty'] = bp.current_quantity or 0.0
            else:
                vals['current_qty'] = 0.0

        # تحقق من القراءة من Order Tracking
        if self.env.context.get('from_order_tracking'):
            raise UserError("Cannot create request lines from Order Tracking (read-only).")

        # ======= إضافة supply_qty الافتراضية إذا لم تُعطَ =======
        if 'supply_qty' not in vals:
            branch_id = request.branch_id if request else None
            if branch_id and product_id:
                bp = self.env['custom_supply.branch_product'].search([
                    ('branch_id', '=', branch_id.id),
                    ('product_id', '=', product_id)
                ], limit=1)
                if bp:
                    max_q = bp.max_quantity or 0.0
                    current_q = vals.get('current_qty', 0.0)
                    suggested = max(0.0, max_q - (current_q or 0.0))
                    vals['supply_qty'] = suggested
        # =======================================================
        if 'current_qty' not in vals or vals['current_qty'] is None:
            vals['current_qty'] = 0.0
        if 'requested_qty' not in vals or vals['requested_qty'] is None:
            vals['requested_qty'] = 0.0

        return super().create(vals)

    # ================================
    # WRITE — منع تعديل الأسطر بعد Done
    # ================================

    def write(self, vals):
        for rec in self:
            request = rec.request_id
            status = request.status
            user = self.env.user

            # لا يسمح بتعديل أي شيء بعد Done
            if status == 'Done':
                raise UserError("You cannot modify lines after the request has been marked done.")

            # Branch Employee: لا يمكن تعديل بعد Submit
            if user.has_group('custom_supply.group_branch_employee'):
                if status != 'InBranch':
                    raise UserError("Branch Employee can only modify lines when the request is in 'InBranch' status.")

            # Supply Manager: يمكن تعديل فقط Supply Qty / Supply Note إذا الطلب في حالة Supply
            if user.has_group('custom_supply.group_supply_manager'):
                if status == 'Supply':
                    allowed_fields = ['supply_qty', 'supply_note']
                    for key in vals.keys():
                        if key not in allowed_fields:
                            raise UserError(f"Supply Manager can only modify fields {allowed_fields}.")
                else:
                    # بعد أن تصبح InWarehouse أو أي حالة أخرى، لا يسمح بالتعديل على الخطوط
                    raise UserError("Supply Manager cannot modify lines once the request is sent to Warehouse or done.")

            # Warehouse Employee: يمكن تعديل فقط Export Qty / Warehouse Note إذا الطلب في حالة InWarehouse
            if user.has_group('custom_supply.group_warehouse_employee'):
                if status == 'InWarehouse':
                    allowed_fields = ['export_qty', 'warehouse_note']
                    for key in vals.keys():
                        if key not in allowed_fields:
                            raise UserError(f"Warehouse Employee can only modify fields {allowed_fields}.")
                else:
                    # بعد Done أو أي حالة أخرى
                    raise UserError(
                        "Warehouse Employee can only modify lines when the request is in 'InWarehouse' status.")

        if self.env.context.get('from_order_tracking'):
            raise UserError("Cannot modify request lines from Order Tracking (read-only).")
        return super().write(vals)

    def unlink(self):
        _logger = logging.getLogger(__name__)
        for rec in self:
            _logger.warning("Attempting to unlink supply_request_line id=%s by user=%s (uid=%s). Stack:\n%s",
                            rec.id, self.env.user.name, self.env.uid, ''.join(traceback.format_stack()))
        return super(SupplyRequestLine, self).unlink()


