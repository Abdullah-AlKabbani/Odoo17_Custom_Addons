# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError


class Branch(models.Model):
    _name = "custom_supply.branch"
    _description = "Branch"


    name = fields.Char(string="Branch Name", required=True)
    location = fields.Char(string="Location")

    # المستخدم المسؤول عن الفرع (واحد فقط)
    user_id = fields.Many2one(
        'res.users',
        string="Branch User",
        help="User responsible for this branch (one user per branch)"
    )

    last_updated = fields.Datetime(
        string="Last Updated",
        compute="_compute_last_updated",
        store=True
    )

    # علاقة مع منتجات الفرع فقط
    product_ids = fields.One2many(
        'custom_supply.branch_product',
        'branch_id',
        string="Products in Branch"
    )

    search_product = fields.Char(
        string="Search Product",
        help="Filter products by name or category",
        store=False,
    )

    # ==============================
    # Search Filed
    # ==============================
    def clear_search(self):
        """
        مسح حقل البحث ثم إعادة تحميل واجهة المستخدم لكي يُعاد تطبيق domain على one2many.
        يتم استدعاء هذا الميثود من زر type="object" في الـ XML.
        """
        for rec in self:
            rec.search_product = False
        return {
            'type': 'ir.actions.client',
            'tag': 'reload'
        }

    # ==============================
    # COMPUTE FIELDS
    # ==============================
    @api.depends('product_ids.write_date')
    def _compute_last_updated(self):
        for branch in self:
            dates = branch.product_ids.mapped('write_date')
            branch.last_updated = max(dates) if dates else False


    # ==============================
    # CREATE OVERRIDE
    # ==============================
    @api.model
    def create(self, vals):
        """بعد إنشاء الفرع، ربط المستخدم المحدد بالفرع وإنشاء المنتجات"""
        branch = super().create(vals)

        # 🔁 ربط المستخدم بالفرع مباشرة (علاقة واحد إلى واحد)
        if branch.user_id:
            # أولاً، إزالة أي ربط سابق لنفس المستخدم
            old_branch = self.search([('user_id', '=', branch.user_id.id), ('id', '!=', branch.id)], limit=1)
            if old_branch:
                old_branch.user_id = False

            # ثم ضبط العلاقة الثنائية
            branch.user_id.sudo().branch_id = branch

        # إنشاء منتجات الفرع
        products = self.env['product.product'].search([
            ('product_tmpl_id.product_for_supply', '=', True)
        ])
        branch_product_model = self.env['custom_supply.branch_product'].sudo()
        existing_pids = branch_product_model.search([('branch_id', '=', branch.id)]).mapped('product_id').ids

        to_create = []
        for product in products:
            if product.id not in existing_pids:
                to_create.append({
                    'branch_id': branch.id,
                    'product_id': product.id,
                    'min_quantity': 0.0,
                    'max_quantity': 0.0,
                    'current_quantity': 0.0,
                    'activate': True,
                })
        if to_create:
            branch_product_model.create(to_create)

        return branch

    # ==============================
    # WRITE OVERRIDE
    # ==============================
    def write(self, vals):
        """تحديث المستخدم المرتبط عند تعديل user_id"""
        res = super().write(vals)

        # إذا تم تغيير المستخدم، حدث العلاقة الثنائية
        if 'user_id' in vals:
            for branch in self:
                if branch.user_id:
                    # إزالة أي فرع قديم للمستخدم الجديد
                    old_branch = self.search([('user_id', '=', branch.user_id.id), ('id', '!=', branch.id)], limit=1)
                    if old_branch:
                        old_branch.user_id = False
                    # ضبط العلاقة العكسية
                    branch.user_id.sudo().branch_id = branch
        return res

    # ==============================
    # ONCHANGE
    # ==============================
    @api.onchange('name')
    def _onchange_name_create_products(self):
        """عند تعبئة الاسم في سجل جديد، نملأ الجدول بالمنتجات افتراضيًا قبل الحفظ"""
        if not self._origin.id and self.name:  # سجل جديد فقط
            products = self.env['product.product'].search([
                ('product_tmpl_id.product_for_supply', '=', True)
            ])
            self.product_ids = [(5, 0, 0)]  # مسح أي سجلات افتراضية
            for product in products:
                self.product_ids += self.env['custom_supply.branch_product'].new({
                    'product_id': product.id,
                    'min_quantity': 0.0,
                    'max_quantity': 0.0,
                    'current_quantity': 0.0,
                    'activate': True,
                })
