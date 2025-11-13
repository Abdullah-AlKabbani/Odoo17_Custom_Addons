# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class SupplyRequest(models.Model):
    _name = "custom_supply.supply_request"
    _description = "Supply Request from Branch"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = "id desc"



    # ============================
    # Fields
    # ============================
    name = fields.Char(
        string="Request Number",
        required=True,
        copy=False,
        readonly=True,
        default='New'
    )
    request_date = fields.Datetime(
        string="Request Date",
        readonly=True,
        default=fields.Datetime.now
    )
    branch_id = fields.Many2one(
        'custom_supply.branch',
        string="Branch",
        required=True,
        default=lambda self: self._default_branch()
    )

    status = fields.Selection([
        ('InBranch', 'In Branch'),
        ('Supply', 'Supply'),
        ('InWarehouse', 'In Warehouse'),
        ('Done', 'Done')
    ], string="Status", default='InBranch', tracking=True)

    line_ids = fields.One2many(
        'custom_supply.supply_request_line',
        'request_id',
        string="Request Lines"
    )

    supply_manager_id = fields.Many2one('res.users', string="Supply Manager", readonly=True)
    warehouse_user_id = fields.Many2one('res.users', string="Warehouse User", readonly=True)

    supply_confirm_date = fields.Datetime("Supply Confirmed On", readonly=True)
    warehouse_export_date = fields.Datetime("Exported On", readonly=True)


    # ============================
    # DEFAULT branch helper
    # ============================
    @api.model
    def _default_branch(self):
        user = self.env.user
        if getattr(user, 'branch_id', False):
            return user.branch_id.id
        branch = self.env['custom_supply.branch'].search([('user_id', '=', user.id)], limit=1)
        return branch.id if branch else False

    # ============================
    # Default_get
    # ============================
    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if 'name' in fields_list and (res.get('name') in (False, 'New')):
            seq_code = 'custom_supply.supply_request'
            try:
                res['name'] = self.env['ir.sequence'].next_by_code(seq_code) or 'New'
            except Exception as e:
                _logger.exception("Failed to generate sequence in default_get: %s", e)
                res['name'] = 'New'
        if 'branch_id' in fields_list and not res.get('branch_id'):
            branch_id = self._default_branch()
            if branch_id:
                res['branch_id'] = branch_id
        return res

    # ============================
    # Create
    # ============================
    @api.model_create_multi
    def create(self, vals_list):
        seq_code = 'custom_supply.supply_request'
        seq = self.env['ir.sequence'].search([('code', '=', seq_code)], limit=1)
        if not seq:
            try:
                seq = self.env['ir.sequence'].create({
                    'name': 'Supply Request',
                    'code': seq_code,
                    'prefix': 'SR',
                    'padding': 4,
                    'implementation': 'standard',
                })
            except Exception as e:
                _logger.exception("Failed to create sequence: %s", e)
                seq = False

        current_user = self.env.user
        user_branch = getattr(current_user, 'branch_id', False)

        for vals in vals_list:
            if vals.get('name', 'New') in ('New', False):
                try:
                    vals['name'] = self.env['ir.sequence'].next_by_code(seq_code) or 'New'
                except Exception as e:
                    _logger.exception("Failed to generate sequence number: %s", e)
                    vals['name'] = 'New'
            if not vals.get('branch_id') and user_branch:
                vals['branch_id'] = user_branch.id
            if not vals.get('request_date'):
                vals['request_date'] = fields.Datetime.now()

        requests = super().create(vals_list)

        for request in requests:
            try:
                if not request.line_ids and request.branch_id:
                    request._fill_basic_products_lines()
                request.message_post(
                    body=f"Supply Request '{request.name}' created for branch '{request.branch_id.name if request.branch_id else 'N/A'}'."
                )
            except Exception as e:
                _logger.exception("Post-create process failed: %s", e)

        return requests

    # ============================
    # Onchange branch
    # ============================
    @api.onchange('branch_id')
    def _onchange_branch_id(self):
        if not self.branch_id:
            self.line_ids = [(5, 0, 0)]
            return
        if not self.line_ids:
            self._fill_basic_products_lines()

    # ============================
    # Fill basic product lines
    # ============================
    def _fill_basic_products_lines(self):
        self.ensure_one()
        try:
            branch_products = (
                self.branch_id.product_ids
                if hasattr(self.branch_id, 'product_ids')
                else self.env['custom_supply.branch_product'].search([('branch_id', '=', self.branch_id.id)])
            )
            if not branch_products:
                return
            filtered_bps = branch_products.filtered(
                lambda bp: hasattr(bp, 'product_id') and bp.product_id and getattr(bp.product_id.product_tmpl_id, 'custom_supply_field_1', '') == 'basic'
            )
            lines = []
            for bp in filtered_bps:
                if not bp.id or not bp.product_id:
                    continue
                lines.append((0, 0, {
                    'product_id': bp.product_id.id,
                    'current_qty': float(bp.current_quantity or 0.0),
                    'suggested_qty': getattr(bp, 'max_quantity', 0.0) or 0.0,
                    'requested_qty': 0.0,
                    'branch_product_id': bp.id,
                }))
            if lines:
                self.line_ids = lines
        except Exception as e:
            _logger.exception("Failed to fill basic products lines: %s", e)

    # ============================
    # Actions
    # ============================
    def action_submit_request(self):
        for rec in self:
            _logger.info("Export START for request %s (id=%s). lines_before=%s", rec.name, rec.id, len(rec.line_ids))
            if self.env.context.get('from_order_tracking'):
                raise UserError("This action is disabled in Order Tracking view.")

            if rec.status != 'InBranch':
                continue
            if not self.env.user.has_group('custom_supply.group_branch_employee'):
                raise UserError("Only Branch Employee can submit this request.")
            if not rec.line_ids:
                raise UserError("Cannot submit an empty request. Please add products before submitting.")

            # تغيير الحالة باستخدام write مع context
            rec.with_context(allow_status_change=True).write({'status': 'Supply'})
            rec.message_post(body=f"Supply Request '{rec.name}' submitted by {self.env.user.name}.")
            _logger.info("Export END for request %s (id=%s). lines_after=%s", rec.name, rec.id, len(rec.line_ids))
        return True

    def action_mark_in_warehouse(self):
        for rec in self:
            if self.env.context.get('from_order_tracking'):
                raise UserError("This action is disabled in Order Tracking view.")

            if rec.status != 'Supply':
                continue
            if not self.env.user.has_group('custom_supply.group_supply_manager'):
                raise UserError("Only Supply Manager can confirm this stage.")

            for line in rec.line_ids:
                if line._origin.id is False:
                    line.current_qty = 0.0
                elif line.current_qty is None:
                    line.current_qty = 0.0
                if line._origin.id is False:
                    line.requested_qty = 0.0
                elif line.requested_qty is None:
                    line.requested_qty = 0.0
                if line.supply_qty is None:
                    line.supply_qty = line.suggested_qty or 0.0

            # تغيير الحالة باستخدام write مع context
            rec.with_context(allow_status_change=True).write({'status': 'InWarehouse'})
            rec.supply_manager_id = self.env.user.id
            rec.supply_confirm_date = fields.Datetime.now()
            rec.message_post(body=f"Supply Request '{rec.name}' sent to Warehouse by {self.env.user.name}.")
        return True

    def action_export(self):
        for rec in self:
            if self.env.context.get('from_order_tracking'):
                raise UserError("This action is disabled in Order Tracking view.")

            if rec.status != 'InWarehouse':
                continue
            if not self.env.user.has_group('custom_supply.group_warehouse_employee'):
                raise UserError("Only Warehouse Employee can export this request.")

            rec.warehouse_user_id = self.env.user.id
            rec.warehouse_export_date = fields.Datetime.now()

            # تغيير الحالة باستخدام write مع context
            rec.with_context(allow_status_change=True).write({'status': 'Done'})

            rec.message_post(body=f"Supply Request '{rec.name}' exported by {self.env.user.name} and marked as Done.")
        return True

    def print_warehouse_request_pdf(self):
        """
        Method to print Supply Request PDF for Warehouse Employees
        """
        return self.env.ref('custom_supply.action_report_supply_request_pdf').report_action(self)

    # ============================
    # Domains for Tabs with Roles
    # ============================
    def _domain_for_tab(self, tab, user):
        """
        Return a domain list appropriate for the given tab and user role.
        """
        if not tab:
            return []

        branch = getattr(user, 'branch_id', False)

        # Identify roles
        is_branch = user.has_group('custom_supply.group_branch_employee')
        is_supply = user.has_group('custom_supply.group_supply_manager')
        is_warehouse = user.has_group('custom_supply.group_warehouse_employee')
        is_high = user.has_group('custom_supply.group_high_manager')

        # =============== Branch Employee ==================
        if is_branch:
            if tab == 'supply_request':
                return [('branch_id', '=', branch.id if branch else 0), ('status', '=', 'InBranch')]
            elif tab == 'order_tracking':
                return [('branch_id', '=', branch.id if branch else 0), ('status', 'in', ['Supply', 'InWarehouse', 'Done'])]
            else:
                return [('id', '=', 0)]

        # =============== Supply Manager ==================
        if is_supply:
            if tab == 'supply_request':
                return [('status', '=', 'Supply')]
            elif tab == 'order_tracking':
                return [('status', 'in', ['InWarehouse', 'Done'])]
            else:
                return [('id', '=', 0)]

        # =============== Warehouse Employee ==================
        if is_warehouse:
            if tab == 'supply_request':
                return [('status', '=', 'InWarehouse')]
            elif tab == 'order_tracking':
                return [('status', '=', 'Done')]
            else:
                return [('id', '=', 0)]

        # =============== High Manager ==================
        if is_high:
            if tab == 'order_tracking':
                return [('status', 'in', ['Supply', 'InWarehouse', 'Done'])]
            else:
                return [('id', '=', 0)]

        # fallback: deny if role not matched
        return [('id', '=', 0)]

    # ============================
    # Override search
    # ============================
    @api.model
    def search(self, args, offset=0, limit=None, order=None, **kwargs):
        """
        Search records with tab domain applied if 'tab' exists in context.
        This avoids recursion by not overriding read().
        """
        user = self.env.user
        tab = self.env.context.get('tab', None)

        if tab:
            tab_domain = self._domain_for_tab(tab.lower(), user)
            if tab_domain:
                args = list(tab_domain) + list(args)

        # تمرير أي kwargs إضافية للأصلية لتجنب TypeError
        return super(SupplyRequest, self).search(args, offset=offset, limit=limit, order=order, **kwargs)

    def write(self, vals):
        # السماح فقط بالكتابة على حقول Chatter أثناء التصفّح من Order Tracking
        chatter_fields = ['message_ids', 'message_follower_ids', 'activity_ids']

        if self.env.context.get('from_order_tracking'):
            # السماح بتعديل Chatter فقط
            non_chatter_fields = [k for k in vals if k not in chatter_fields]
            if non_chatter_fields:
                raise UserError("You cannot modify this record from the Order Tracking view except for Chatter fields.")

        #  منع أي تعديل لحقل الحالة (status) يدويًا أو عبر السحب في Kanban
        if 'status' in vals:
            # السماح فقط إذا flag محدد موجود في السياق
            if not self.env.context.get('allow_status_change'):
                raise UserError("You cannot change the status of a supply request manually.")

        return super(SupplyRequest, self).write(vals)

    def unlink(self):
        if self.env.context.get('from_order_tracking'):
            raise UserError("Cannot delete records from Order Tracking (read-only).")
        return super(SupplyRequest, self).unlink()