# -*- coding: utf-8 -*-
import traceback
import logging

from odoo import models, fields, api
from odoo.exceptions import UserError


class SupplyRequestLine(models.Model):
    _name = "custom_supply.supply_request_line"
    _description = "Supply Request Line"

    # ==============================================================
    # Basic Fields
    # ==============================================================

    request_id = fields.Many2one('custom_supply.supply_request',string="Request",ondelete='cascade')
    allowed_product_ids = fields.Many2many('product.product',string='Allowed Products',compute='_compute_allowed_products',store=True)
    product_id = fields.Many2one(        'product.product',string="Product",required=True,)
    unit_name = fields.Char(string="Unit",compute="_compute_unit_name",store=False,readonly=True)
    current_qty = fields.Float(string="Current Quantity",required=True, default=0.0)
    suggested_qty = fields.Float(string="Suggested Quantity",compute="_compute_suggested_qty",store=True)
    requested_qty = fields.Float(string="Requested Quantity",required=True,default=0.0)
    note = fields.Text(string="Note / Reason")
    branch_product_id = fields.Many2one( 'custom_supply.branch_product',string="Branch Product Link")

    supply_qty = fields.Float(string="Supply Quantity", help="Quantity approved by Supply Manager")
    supply_note = fields.Text(string="Supply Note", help="Note / reason from Supply Manager")

    export_qty = fields.Float(string="Export Quantity",help="Quantity actually exported by Warehouse")
    warehouse_note = fields.Text(string="Warehouse Note",help="Note / reason from Warehouse")

    # ==============================================================
    # Compute Allowed Products per Branch
    # ==============================================================
    @api.depends('request_id.branch_id')
    def _compute_allowed_products(self):
        Product = self.env['product.product']
        for rec in self:
            branch = rec.request_id.branch_id if rec.request_id else self.env.context.get('branch_id')
            if branch:
                rec.allowed_product_ids = branch.product_ids.filtered('activate').mapped('product_id') or Product
            else:
                rec.allowed_product_ids = Product

    @api.onchange('request_id')
    def _onchange_request_id(self):
        for rec in self:
            branch = rec.request_id.branch_id if rec.request_id else self.env.context.get('branch_id')
            if branch:
                rec.allowed_product_ids = branch.product_ids.filtered('activate').mapped('product_id')
            else:
                rec.allowed_product_ids = self.env['product.product']


    # ==============================================================
    # Compute Unit Name
    # ==============================================================

    @api.depends('product_id')
    def _compute_unit_name(self):
        """Compute unit name from product's supply unit."""
        for rec in self:
            if rec.product_id and rec.product_id.product_tmpl_id.supply_unit_id:
                rec.unit_name = rec.product_id.product_tmpl_id.supply_unit_id.name
            else:
                rec.unit_name = ''

    # ==============================================================
    # Compute Suggested Quantity
    # ==============================================================

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
                max_q = branch_product.max_quantity or 0.0
                line.suggested_qty = max(0.0, max_q - (line.current_qty or 0.0))
            else:
                line.suggested_qty = 0.0

    # ==============================================================
    # CREATE rules
    # ==============================================================

    @api.model
    def create(self, vals):
        request = self.env['custom_supply.supply_request'].browse(
            vals.get('request_id')
        )
        user = self.env.user

        # Restrict by status
        if request and request.status not in ('InBranch', 'Supply'):
            raise UserError(
                "You cannot add new lines when the request is not in 'InBranch' or 'Supply' status."
            )

        # Permissions by user role
        if request:
            if request.status == 'InBranch' and not user.has_group('custom_supply.group_branch_employee'):
                raise UserError("Only Branch Employee can add lines in 'InBranch' status.")

            if request.status == 'Supply' and not user.has_group('custom_supply.group_supply_manager'):
                raise UserError("Only Supply Manager can add lines in 'Supply' status.")

        # Prevent adding invalid product
        product_id = vals.get('product_id')
        branch_product_id = vals.get('branch_product_id')

        if request and product_id:
            bp = self.env['custom_supply.branch_product'].search([
                ('branch_id', '=', request.branch_id.id),
                ('product_id', '=', product_id)
            ], limit=1)

            if not bp:
                raise UserError(
                    f"Cannot add product not defined in branch '{request.branch_id.name}'"
                )

            if not bp.activate:
                raise UserError(
                    f"Product '{bp.product_id.name}' is disabled in branch '{request.branch_id.name}' and cannot be added."
                )

            if not branch_product_id:
                vals['branch_product_id'] = bp.id

        # Auto-fill current quantity
        if not vals.get('current_qty') and request and product_id:
            bp = self.env['custom_supply.branch_product'].search([
                ('branch_id', '=', request.branch_id.id),
                ('product_id', '=', product_id)
            ], limit=1)

            vals['current_qty'] = bp.current_quantity if bp else 0.0

        # Prevent creation from order tracking
        if self.env.context.get('from_order_tracking'):
            raise UserError("Cannot create request lines from Order Tracking (read-only).")

        # Auto compute supply_qty
        if 'supply_qty' not in vals:
            if request and product_id:
                bp = self.env['custom_supply.branch_product'].search([
                    ('branch_id', '=', request.branch_id.id),
                    ('product_id', '=', product_id)
                ], limit=1)

                if bp:
                    max_q = bp.max_quantity or 0.0
                    current_q = vals.get('current_qty', 0.0)
                    vals['supply_qty'] = max(0.0, max_q - (current_q or 0.0))

        # No empty fields
        vals.setdefault('current_qty', 0.0)
        vals.setdefault('requested_qty', 0.0)

        return super().create(vals)

    # ==============================================================
    # WRITE rules
    # ==============================================================

    def write(self, vals):
        user = self.env.user

        for rec in self:
            request = rec.request_id
            status = request.status

            if status == 'Done':
                raise UserError("You cannot modify lines after done.")

            if user.has_group('custom_supply.group_branch_employee'):
                if status != 'InBranch':
                    raise UserError("Branch Employee can only modify lines in 'InBranch'.")

            if user.has_group('custom_supply.group_supply_manager'):
                if status == 'Supply':
                    allowed_fields = ['supply_qty', 'supply_note']
                    for key in vals:
                        if key not in allowed_fields:
                            raise UserError(f"Supply Manager can only modify: {allowed_fields}")
                else:
                    raise UserError("Supply Manager cannot modify lines now.")

            if user.has_group('custom_supply.group_warehouse_employee'):
                if status == 'InWarehouse':
                    allowed_fields = ['export_qty', 'warehouse_note']
                    for key in vals:
                        if key not in allowed_fields:
                            raise UserError(f"Warehouse Employee can only modify: {allowed_fields}")
                else:
                    raise UserError("Warehouse Employee cannot modify lines in this status.")

        if self.env.context.get('from_order_tracking'):
            raise UserError("Cannot modify lines from Order Tracking (read-only).")

        return super().write(vals)

    # ==============================================================
    # Unlink logging
    # ==============================================================

    def unlink(self):
        _logger = logging.getLogger(__name__)
        for rec in self:
            _logger.warning(
                "Attempting to unlink supply_request_line id=%s by user=%s (uid=%s). Stack:\n%s",
                rec.id, self.env.user.name, self.env.uid,
                ''.join(traceback.format_stack())
            )
        return super(SupplyRequestLine, self).unlink()
