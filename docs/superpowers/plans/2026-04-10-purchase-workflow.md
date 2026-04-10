# Purchase Workflow Enhancement — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend `co_warehouse_extended` to cover a complete procurement workflow: product requests with stock checks, N-level approval, supplier scoring, quotation comparison, partial receipt tracking, and automatic journal entries.

**Architecture:** Extend the existing `co_warehouse_extended` module with 6 new models and extensions to 4 existing models. The workflow is linear: product request → stock check → split/transfer → approval → supplier scoring → RFQ → quotation comparison → PO → receipt → journal entry → inventory update.

**Tech Stack:** Odoo 19.0, Python 3.12, PostgreSQL 15, XML views, ir.model.access CSV security

---

## File Map

### New Files

| File | Responsibility |
|---|---|
| `models/co_product_request.py` | Product request model + stock check + split logic |
| `models/co_product_request_line.py` | Product request line items with availability |
| `models/co_purchase_approval_level.py` | Configurable N-level approval tiers |
| `models/co_purchase_approval_line.py` | Per-request approval step tracking |
| `models/co_supplier_score.py` | Multi-criteria supplier scoring |
| `models/co_quotation_comparison.py` | Side-by-side RFQ comparison + ranking |
| `models/res_config_settings.py` | Purchase workflow settings in Settings UI |
| `models/res_company.py` | Company-level purchase workflow fields |
| `views/co_product_request_views.xml` | Product request form/tree/search views |
| `views/co_purchase_approval_level_views.xml` | Approval level configuration views |
| `views/co_supplier_score_views.xml` | Supplier score views |
| `views/co_quotation_comparison_views.xml` | Quotation comparison views |
| `views/res_config_settings_views.xml` | Settings page extension |
| `data/product_request_sequence.xml` | Sequence for PREQ-XXXXX |

### Modified Files

| File | Changes |
|---|---|
| `__manifest__.py` | Add new depends (`hr`), new data files |
| `models/__init__.py` | Import new model files |
| `models/co_purchase_request.py` | Add approval fields, supplier eval, RFQ creation |
| `models/co_purchase_request_line.py` | No changes needed |
| `models/stock_picking.py` | Add journal entry generation, fulfillment tracking on PO |
| `models/stock_warehouse.py` | Add `purchase_split_mode` field |
| `security/co_warehouse_security.xml` | Add approver group |
| `security/ir.model.access.csv` | Add access rules for new models |
| `views/co_purchase_request_views.xml` | Add approval timeline, supplier eval tab |
| `views/co_menus.xml` | Add new menu items |

---

## Task 1: Company Settings & Configuration Models

**Files:**
- Create: `custom-addons/co_warehouse_extended/models/res_company.py`
- Create: `custom-addons/co_warehouse_extended/models/res_config_settings.py`
- Create: `custom-addons/co_warehouse_extended/views/res_config_settings_views.xml`
- Modify: `custom-addons/co_warehouse_extended/models/__init__.py`
- Modify: `custom-addons/co_warehouse_extended/models/stock_warehouse.py`
- Modify: `custom-addons/co_warehouse_extended/__manifest__.py`

- [ ] **Step 1: Create `models/res_company.py`**

```python
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    purchase_split_mode = fields.Selection([
        ('auto', 'Automatic Split'),
        ('manual', 'User Decides'),
    ], string='Stock Availability Split Mode', default='auto',
        help='How to handle partially available stock on product requests.')
    default_supplier_count = fields.Integer(
        string='Default Supplier Count for RFQs', default=3,
        help='Number of top-ranked suppliers to request quotations from.')
    supplier_weight_price = fields.Float(string='Price Weight', default=40.0)
    supplier_weight_delivery = fields.Float(string='Delivery Weight', default=25.0)
    supplier_weight_quality = fields.Float(string='Quality Weight', default=20.0)
    supplier_weight_compliance = fields.Float(string='Compliance Weight', default=15.0)
    purchase_journal_mode = fields.Selection([
        ('auto_entry', 'Automatic Journal Entry'),
        ('vendor_bill', 'Vendor Bill'),
    ], string='Receipt Journal Mode', default='vendor_bill',
        help='How to create accounting entries upon goods receipt.')
```

- [ ] **Step 2: Create `models/res_config_settings.py`**

```python
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    purchase_split_mode = fields.Selection(
        related='company_id.purchase_split_mode', readonly=False)
    default_supplier_count = fields.Integer(
        related='company_id.default_supplier_count', readonly=False)
    supplier_weight_price = fields.Float(
        related='company_id.supplier_weight_price', readonly=False)
    supplier_weight_delivery = fields.Float(
        related='company_id.supplier_weight_delivery', readonly=False)
    supplier_weight_quality = fields.Float(
        related='company_id.supplier_weight_quality', readonly=False)
    supplier_weight_compliance = fields.Float(
        related='company_id.supplier_weight_compliance', readonly=False)
    purchase_journal_mode = fields.Selection(
        related='company_id.purchase_journal_mode', readonly=False)
```

- [ ] **Step 3: Create `views/res_config_settings_views.xml`**

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="res_config_settings_view_form_purchase_workflow" model="ir.ui.view">
        <field name="name">res.config.settings.view.form.inherit.purchase.workflow</field>
        <field name="model">res.config.settings</field>
        <field name="inherit_id" ref="purchase.res_config_settings_view_form"/>
        <field name="arch" type="xml">
            <xpath expr="//app[@name='purchase']" position="inside">
                <block title="Purchase Workflow" name="purchase_workflow_setting">
                    <setting string="Stock Availability Split Mode"
                             help="How to handle partially available stock on product requests.">
                        <field name="purchase_split_mode" widget="radio"/>
                    </setting>
                    <setting string="Default Supplier Count for RFQs"
                             help="Number of top-ranked suppliers to request quotations from by default.">
                        <field name="default_supplier_count"/>
                    </setting>
                    <setting string="Receipt Journal Mode"
                             help="How to create accounting entries upon goods receipt.">
                        <field name="purchase_journal_mode" widget="radio"/>
                    </setting>
                    <setting string="Supplier Scoring Weights"
                             help="Weights for multi-criteria supplier evaluation (should total 100).">
                        <div class="row mt8">
                            <label for="supplier_weight_price" class="col-3 col-lg-3 o_light_label"/>
                            <field name="supplier_weight_price" class="col-2"/>
                            <label for="supplier_weight_delivery" class="col-3 col-lg-3 o_light_label"/>
                            <field name="supplier_weight_delivery" class="col-2"/>
                        </div>
                        <div class="row mt8">
                            <label for="supplier_weight_quality" class="col-3 col-lg-3 o_light_label"/>
                            <field name="supplier_weight_quality" class="col-2"/>
                            <label for="supplier_weight_compliance" class="col-3 col-lg-3 o_light_label"/>
                            <field name="supplier_weight_compliance" class="col-2"/>
                        </div>
                    </setting>
                </block>
            </xpath>
        </field>
    </record>
</odoo>
```

- [ ] **Step 4: Add `purchase_split_mode` to `stock_warehouse.py`**

Add after existing fields in `/Users/manuelcaro/Odoo/custom-addons/co_warehouse_extended/models/stock_warehouse.py`:

```python
    purchase_split_mode = fields.Selection([
        ('auto', 'Automatic Split'),
        ('manual', 'User Decides'),
        ('company_default', 'Use Company Setting'),
    ], string='Stock Availability Split Mode', default='company_default',
        help='Override company setting for this warehouse.')
```

- [ ] **Step 5: Update `models/__init__.py`**

Add these imports to the existing file:

```python
from . import res_company
from . import res_config_settings
```

- [ ] **Step 6: Update `__manifest__.py`**

Add `'hr'` to the `depends` list. Add these to the `data` list:

```python
'views/res_config_settings_views.xml',
```

- [ ] **Step 7: Commit**

```bash
git add custom-addons/co_warehouse_extended/models/res_company.py \
        custom-addons/co_warehouse_extended/models/res_config_settings.py \
        custom-addons/co_warehouse_extended/views/res_config_settings_views.xml \
        custom-addons/co_warehouse_extended/models/stock_warehouse.py \
        custom-addons/co_warehouse_extended/models/__init__.py \
        custom-addons/co_warehouse_extended/__manifest__.py
git commit -m "feat: add purchase workflow company settings and configuration"
```

---

## Task 2: Product Request Model & Lines

**Files:**
- Create: `custom-addons/co_warehouse_extended/models/co_product_request.py`
- Create: `custom-addons/co_warehouse_extended/models/co_product_request_line.py`
- Create: `custom-addons/co_warehouse_extended/data/product_request_sequence.xml`
- Modify: `custom-addons/co_warehouse_extended/models/__init__.py`
- Modify: `custom-addons/co_warehouse_extended/__manifest__.py`

- [ ] **Step 1: Create `data/product_request_sequence.xml`**

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <data noupdate="1">
        <record id="seq_co_product_request" model="ir.sequence">
            <field name="name">Product Request</field>
            <field name="code">co.product.request</field>
            <field name="prefix">PREQ-</field>
            <field name="padding">5</field>
        </record>
    </data>
</odoo>
```

- [ ] **Step 2: Create `models/co_product_request_line.py`**

```python
from odoo import api, fields, models


class CoProductRequestLine(models.Model):
    _name = 'co.product.request.line'
    _description = 'Product Request Line'
    _order = 'sequence, id'

    sequence = fields.Integer(default=10)
    request_id = fields.Many2one(
        'co.product.request', required=True, ondelete='cascade', index=True)
    product_id = fields.Many2one('product.product', required=True)
    uom_id = fields.Many2one(
        'uom.uom', related='product_id.uom_id', store=True, readonly=True)
    qty_requested = fields.Float(string='Quantity Requested', required=True, default=1.0)
    qty_available = fields.Float(
        string='Available Stock', readonly=True,
        help='Quantity available in warehouse at time of stock check.')
    qty_to_transfer = fields.Float(string='Qty to Transfer')
    qty_to_purchase = fields.Float(string='Qty to Purchase')
    line_state = fields.Selection([
        ('pending', 'Pending'),
        ('available', 'Available'),
        ('partial', 'Partially Available'),
        ('unavailable', 'Unavailable'),
    ], string='Availability', default='pending', readonly=True)
    company_id = fields.Many2one(
        related='request_id.company_id', store=True)
```

- [ ] **Step 3: Create `models/co_product_request.py`**

```python
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class CoProductRequest(models.Model):
    _name = 'co.product.request'
    _description = 'Product Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name desc'

    name = fields.Char(
        string='Reference', required=True, copy=False,
        readonly=True, default='New')
    requester_id = fields.Many2one(
        'res.users', string='Requested By', required=True,
        default=lambda self: self.env.user, tracking=True)
    department_id = fields.Many2one('hr.department', tracking=True)
    company_id = fields.Many2one(
        'res.company', required=True,
        default=lambda self: self.env.company)
    warehouse_id = fields.Many2one(
        'stock.warehouse', string='Source Warehouse', required=True,
        default=lambda self: self.env['stock.warehouse'].search(
            [('company_id', '=', self.env.company.id)], limit=1),
        tracking=True)
    date_request = fields.Date(
        string='Request Date', required=True,
        default=fields.Date.context_today, tracking=True)
    line_ids = fields.One2many(
        'co.product.request.line', 'request_id', string='Requested Products')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('stock_check', 'Stock Checked'),
        ('splitting', 'Awaiting Split Decision'),
        ('processed', 'Processed'),
        ('done', 'Done'),
        ('cancel', 'Cancelled'),
    ], default='draft', tracking=True, string='Status')
    picking_ids = fields.Many2many(
        'stock.picking', string='Internal Transfers',
        copy=False)
    purchase_request_id = fields.Many2one(
        'co.purchase.request', string='Purchase Request',
        readonly=True, copy=False)
    notes = fields.Text()
    picking_count = fields.Integer(compute='_compute_picking_count')
    has_purchase = fields.Boolean(compute='_compute_has_purchase')

    @api.depends('picking_ids')
    def _compute_picking_count(self):
        for rec in self:
            rec.picking_count = len(rec.picking_ids)

    @api.depends('purchase_request_id')
    def _compute_has_purchase(self):
        for rec in self:
            rec.has_purchase = bool(rec.purchase_request_id)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'co.product.request') or 'New'
        return super().create(vals_list)

    def _get_effective_split_mode(self):
        """Return the effective split mode considering warehouse override."""
        self.ensure_one()
        wh_mode = self.warehouse_id.purchase_split_mode
        if wh_mode and wh_mode != 'company_default':
            return wh_mode
        return self.company_id.purchase_split_mode or 'auto'

    def action_check_availability(self):
        """Check stock availability for all lines in the selected warehouse."""
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_('Please add at least one product line.'))
        warehouse = self.warehouse_id
        location = warehouse.lot_stock_id
        for line in self.line_ids:
            qty = line.product_id.with_context(
                location=location.id,
                warehouse_id=warehouse.id,
            ).qty_available
            line.qty_available = qty
            if qty >= line.qty_requested:
                line.line_state = 'available'
                line.qty_to_transfer = line.qty_requested
                line.qty_to_purchase = 0.0
            elif qty > 0:
                line.line_state = 'partial'
                line.qty_to_transfer = qty
                line.qty_to_purchase = line.qty_requested - qty
            else:
                line.line_state = 'unavailable'
                line.qty_to_transfer = 0.0
                line.qty_to_purchase = line.qty_requested

        split_mode = self._get_effective_split_mode()
        if split_mode == 'auto':
            self.state = 'stock_check'
            self.action_process()
        else:
            has_partial = any(
                l.line_state in ('partial', 'unavailable') for l in self.line_ids)
            if has_partial:
                self.state = 'splitting'
            else:
                self.state = 'stock_check'
                self.action_process()

    def action_confirm_split(self):
        """User confirms the split quantities (manual mode)."""
        self.ensure_one()
        for line in self.line_ids:
            if line.qty_to_transfer + line.qty_to_purchase != line.qty_requested:
                raise UserError(_(
                    'Line "%s": Transfer qty + Purchase qty must equal Requested qty (%s).',
                    line.product_id.display_name, line.qty_requested))
            if line.qty_to_transfer > line.qty_available:
                raise UserError(_(
                    'Line "%s": Cannot transfer more than available stock (%s).',
                    line.product_id.display_name, line.qty_available))
        self.action_process()

    def action_process(self):
        """Generate internal transfer and/or purchase request."""
        self.ensure_one()
        transfer_lines = self.line_ids.filtered(lambda l: l.qty_to_transfer > 0)
        purchase_lines = self.line_ids.filtered(lambda l: l.qty_to_purchase > 0)

        if transfer_lines:
            self._create_internal_transfer(transfer_lines)
        if purchase_lines:
            self._create_purchase_request(purchase_lines)

        self.state = 'processed'

    def _create_internal_transfer(self, lines):
        """Create a stock.picking internal transfer for available stock."""
        warehouse = self.warehouse_id
        picking_type = self.env['stock.picking.type'].search([
            ('code', '=', 'internal'),
            ('warehouse_id', '=', warehouse.id),
        ], limit=1)
        if not picking_type:
            raise UserError(_(
                'No internal transfer operation type found for warehouse %s.',
                warehouse.name))
        picking_vals = {
            'picking_type_id': picking_type.id,
            'location_id': warehouse.lot_stock_id.id,
            'location_dest_id': picking_type.default_location_dest_id.id or warehouse.lot_stock_id.id,
            'origin': self.name,
            'scheduled_date': fields.Datetime.now(),
            'move_ids': [(0, 0, {
                'name': line.product_id.display_name,
                'product_id': line.product_id.id,
                'product_uom_qty': line.qty_to_transfer,
                'product_uom': line.uom_id.id,
                'location_id': warehouse.lot_stock_id.id,
                'location_dest_id': picking_type.default_location_dest_id.id or warehouse.lot_stock_id.id,
            }) for line in lines],
        }
        picking = self.env['stock.picking'].create(picking_vals)
        picking.action_confirm()
        self.picking_ids = [(4, picking.id)]

    def _create_purchase_request(self, lines):
        """Create a co.purchase.request for items needing purchase."""
        pr_vals = {
            'user_id': self.requester_id.id,
            'department_id': self.department_id.id,
            'company_id': self.company_id.id,
            'reason': _('Generated from product request %s', self.name),
            'line_ids': [(0, 0, {
                'product_id': line.product_id.id,
                'quantity': line.qty_to_purchase,
                'estimated_price': line.product_id.standard_price,
                'supplier_id': (
                    line.product_id.seller_ids[:1].partner_id.id
                    if line.product_id.seller_ids else False),
            }) for line in lines],
        }
        purchase_request = self.env['co.purchase.request'].create(pr_vals)
        self.purchase_request_id = purchase_request.id

    def action_done(self):
        self.write({'state': 'done'})

    def action_cancel(self):
        self.write({'state': 'cancel'})

    def action_draft(self):
        self.write({'state': 'draft'})
        for line in self.line_ids:
            line.write({
                'qty_available': 0,
                'qty_to_transfer': 0,
                'qty_to_purchase': 0,
                'line_state': 'pending',
            })

    def action_view_pickings(self):
        self.ensure_one()
        action = self.env['ir.actions.actions']._for_xml_id(
            'stock.action_picking_tree_all')
        action['domain'] = [('id', 'in', self.picking_ids.ids)]
        return action

    def action_view_purchase_request(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'co.purchase.request',
            'view_mode': 'form',
            'res_id': self.purchase_request_id.id,
        }
```

- [ ] **Step 4: Update `models/__init__.py`**

Add these imports:

```python
from . import co_product_request
from . import co_product_request_line
```

- [ ] **Step 5: Update `__manifest__.py`**

Add to `depends`: `'hr'`

Add to `data` list (before menus):

```python
'data/product_request_sequence.xml',
```

- [ ] **Step 6: Commit**

```bash
git add custom-addons/co_warehouse_extended/models/co_product_request.py \
        custom-addons/co_warehouse_extended/models/co_product_request_line.py \
        custom-addons/co_warehouse_extended/data/product_request_sequence.xml \
        custom-addons/co_warehouse_extended/models/__init__.py \
        custom-addons/co_warehouse_extended/__manifest__.py
git commit -m "feat: add product request model with stock availability check and split logic"
```

---

## Task 3: Product Request Views

**Files:**
- Create: `custom-addons/co_warehouse_extended/views/co_product_request_views.xml`

Note: This is a NEW file — not the existing `co_purchase_request_views.xml`.

- [ ] **Step 1: Create `views/co_product_request_views.xml`**

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <!-- Form View -->
    <record id="co_product_request_view_form" model="ir.ui.view">
        <field name="name">co.product.request.form</field>
        <field name="model">co.product.request</field>
        <field name="arch" type="xml">
            <form>
                <header>
                    <button name="action_check_availability"
                            string="Check Availability"
                            type="object"
                            class="oe_highlight"
                            invisible="state != 'draft'"/>
                    <button name="action_confirm_split"
                            string="Confirm Split"
                            type="object"
                            class="oe_highlight"
                            invisible="state != 'splitting'"/>
                    <button name="action_done"
                            string="Mark Done"
                            type="object"
                            invisible="state != 'processed'"/>
                    <button name="action_cancel"
                            string="Cancel"
                            type="object"
                            invisible="state in ('done', 'cancel')"/>
                    <button name="action_draft"
                            string="Reset to Draft"
                            type="object"
                            invisible="state not in ('cancel', 'stock_check')"/>
                    <field name="state" widget="statusbar"
                           statusbar_visible="draft,stock_check,processed,done"/>
                </header>
                <sheet>
                    <div class="oe_button_box" name="button_box">
                        <button name="action_view_pickings"
                                type="object"
                                class="oe_stat_button"
                                icon="fa-truck"
                                invisible="picking_count == 0">
                            <field name="picking_count" widget="statinfo"
                                   string="Transfers"/>
                        </button>
                        <button name="action_view_purchase_request"
                                type="object"
                                class="oe_stat_button"
                                icon="fa-shopping-cart"
                                invisible="not has_purchase">
                            <span class="o_stat_text">Purchase Request</span>
                        </button>
                    </div>
                    <div class="oe_title">
                        <h1><field name="name" readonly="1"/></h1>
                    </div>
                    <group>
                        <group>
                            <field name="requester_id"/>
                            <field name="department_id"/>
                            <field name="date_request"/>
                        </group>
                        <group>
                            <field name="warehouse_id"/>
                            <field name="company_id" groups="base.group_multi_company"/>
                        </group>
                    </group>
                    <notebook>
                        <page string="Products" name="products">
                            <field name="line_ids"
                                   readonly="state not in ('draft', 'splitting')">
                                <list editable="bottom">
                                    <field name="sequence" widget="handle"/>
                                    <field name="product_id"/>
                                    <field name="qty_requested"/>
                                    <field name="uom_id" readonly="1"/>
                                    <field name="qty_available" readonly="1"
                                           invisible="parent.state == 'draft'"
                                           decoration-success="line_state == 'available'"
                                           decoration-warning="line_state == 'partial'"
                                           decoration-danger="line_state == 'unavailable'"/>
                                    <field name="qty_to_transfer"
                                           invisible="parent.state == 'draft'"
                                           readonly="parent.state != 'splitting'"/>
                                    <field name="qty_to_purchase"
                                           invisible="parent.state == 'draft'"
                                           readonly="parent.state != 'splitting'"/>
                                    <field name="line_state" invisible="parent.state == 'draft'"
                                           widget="badge"
                                           decoration-success="line_state == 'available'"
                                           decoration-warning="line_state == 'partial'"
                                           decoration-danger="line_state == 'unavailable'"/>
                                </list>
                            </field>
                        </page>
                        <page string="Notes" name="notes">
                            <field name="notes" placeholder="Additional notes..."/>
                        </page>
                    </notebook>
                </sheet>
                <chatter/>
            </form>
        </field>
    </record>

    <!-- List View -->
    <record id="co_product_request_view_list" model="ir.ui.view">
        <field name="name">co.product.request.list</field>
        <field name="model">co.product.request</field>
        <field name="arch" type="xml">
            <list decoration-info="state == 'draft'"
                  decoration-warning="state == 'splitting'"
                  decoration-success="state in ('processed', 'done')"
                  decoration-muted="state == 'cancel'">
                <field name="name"/>
                <field name="date_request"/>
                <field name="requester_id" widget="many2one_avatar_user"/>
                <field name="department_id" optional="show"/>
                <field name="warehouse_id"/>
                <field name="state" widget="badge"
                       decoration-info="state == 'draft'"
                       decoration-warning="state == 'splitting'"
                       decoration-success="state in ('processed', 'done')"
                       decoration-muted="state == 'cancel'"/>
            </list>
        </field>
    </record>

    <!-- Search View -->
    <record id="co_product_request_view_search" model="ir.ui.view">
        <field name="name">co.product.request.search</field>
        <field name="model">co.product.request</field>
        <field name="arch" type="xml">
            <search>
                <field name="name"/>
                <field name="requester_id"/>
                <field name="department_id"/>
                <filter name="filter_my" string="My Requests"
                        domain="[('requester_id', '=', uid)]"/>
                <filter name="filter_draft" string="Draft"
                        domain="[('state', '=', 'draft')]"/>
                <filter name="filter_processed" string="Processed"
                        domain="[('state', '=', 'processed')]"/>
                <separator/>
                <group expand="0" string="Group By">
                    <filter name="group_state" string="Status"
                            context="{'group_by': 'state'}"/>
                    <filter name="group_requester" string="Requester"
                            context="{'group_by': 'requester_id'}"/>
                    <filter name="group_department" string="Department"
                            context="{'group_by': 'department_id'}"/>
                    <filter name="group_warehouse" string="Warehouse"
                            context="{'group_by': 'warehouse_id'}"/>
                </group>
            </search>
        </field>
    </record>

    <!-- Actions -->
    <record id="action_co_product_request" model="ir.actions.act_window">
        <field name="name">Product Requests</field>
        <field name="res_model">co.product.request</field>
        <field name="view_mode">list,form</field>
        <field name="search_view_id" ref="co_product_request_view_search"/>
        <field name="context">{'search_default_filter_my': 1}</field>
        <field name="path">product-requests</field>
        <field name="help" type="html">
            <p class="o_view_nocontent_smiling_face">
                Create a product request
            </p>
            <p>Request products and the system will check stock availability,
               generate transfers for available items, and create purchase
               requests for items that need to be purchased.</p>
        </field>
    </record>
</odoo>
```

- [ ] **Step 2: Update `__manifest__.py`**

Add to `data` list (before menus):

```python
'views/co_product_request_views.xml',
```

- [ ] **Step 3: Update `views/co_menus.xml`**

Add a new menu entry for product requests under the Purchase menu root. Add before the existing `menu_purchase_request_root`:

```xml
    <menuitem id="menu_product_request"
              name="Product Requests"
              parent="purchase.menu_purchase_root"
              action="action_co_product_request"
              sequence="3"/>
```

- [ ] **Step 4: Commit**

```bash
git add custom-addons/co_warehouse_extended/views/co_product_request_views.xml \
        custom-addons/co_warehouse_extended/views/co_menus.xml \
        custom-addons/co_warehouse_extended/__manifest__.py
git commit -m "feat: add product request views and menu"
```

---

## Task 4: N-Level Approval Models

**Files:**
- Create: `custom-addons/co_warehouse_extended/models/co_purchase_approval_level.py`
- Create: `custom-addons/co_warehouse_extended/models/co_purchase_approval_line.py`
- Modify: `custom-addons/co_warehouse_extended/models/__init__.py`

- [ ] **Step 1: Create `models/co_purchase_approval_level.py`**

```python
from odoo import fields, models


class CoPurchaseApprovalLevel(models.Model):
    _name = 'co.purchase.approval.level'
    _description = 'Purchase Approval Level'
    _order = 'company_id, department_id, sequence'

    company_id = fields.Many2one(
        'res.company', required=True,
        default=lambda self: self.env.company)
    department_id = fields.Many2one(
        'hr.department', string='Department',
        help='Leave empty for company-wide fallback levels.')
    sequence = fields.Integer(string='Approval Order', default=10)
    name = fields.Char(string='Level Name', required=True)
    min_amount = fields.Float(string='Minimum Amount', required=True)
    max_amount = fields.Float(
        string='Maximum Amount',
        help='Set to 0 for unlimited.')
    currency_id = fields.Many2one(
        'res.currency', required=True,
        default=lambda self: self.env.company.currency_id)
    approver_ids = fields.Many2many(
        'res.users',
        'co_approval_level_users_rel',
        'level_id', 'user_id',
        string='Authorized Approvers')
```

- [ ] **Step 2: Create `models/co_purchase_approval_line.py`**

```python
from odoo import fields, models


class CoPurchaseApprovalLine(models.Model):
    _name = 'co.purchase.approval.line'
    _description = 'Purchase Approval Line'
    _order = 'sequence, id'

    purchase_request_id = fields.Many2one(
        'co.purchase.request', required=True,
        ondelete='cascade', index=True)
    approval_level_id = fields.Many2one(
        'co.purchase.approval.level', string='Approval Level',
        required=True)
    sequence = fields.Integer(
        related='approval_level_id.sequence', store=True)
    approver_id = fields.Many2one(
        'res.users', string='Approved By', readonly=True)
    date = fields.Datetime(string='Date', readonly=True)
    state = fields.Selection([
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ], default='pending', string='Status', readonly=True)
    notes = fields.Text(string='Notes')
```

- [ ] **Step 3: Update `models/__init__.py`**

Add:

```python
from . import co_purchase_approval_level
from . import co_purchase_approval_line
```

- [ ] **Step 4: Commit**

```bash
git add custom-addons/co_warehouse_extended/models/co_purchase_approval_level.py \
        custom-addons/co_warehouse_extended/models/co_purchase_approval_line.py \
        custom-addons/co_warehouse_extended/models/__init__.py
git commit -m "feat: add N-level purchase approval models"
```

---

## Task 5: Integrate Approval into Purchase Request

**Files:**
- Modify: `custom-addons/co_warehouse_extended/models/co_purchase_request.py`
- Modify: `custom-addons/co_warehouse_extended/views/co_purchase_request_views.xml`

- [ ] **Step 1: Add approval fields and methods to `co_purchase_request.py`**

Add these fields after the existing `priority` field:

```python
    estimated_amount = fields.Float(
        string='Estimated Amount',
        compute='_compute_estimated_amount', store=True)
    currency_id = fields.Many2one(
        'res.currency', related='company_id.currency_id', store=True)
    approval_line_ids = fields.One2many(
        'co.purchase.approval.line', 'purchase_request_id',
        string='Approval Steps')
    approval_state = fields.Selection([
        ('no_approval', 'No Approval Needed'),
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ], compute='_compute_approval_state', store=True, string='Approval Status')
    supplier_count = fields.Integer(
        string='Number of Suppliers for RFQ',
        help='Override company default. 0 = use company setting.')
    comparison_id = fields.Many2one(
        'co.quotation.comparison', string='Quotation Comparison',
        readonly=True, copy=False)
    product_request_id = fields.Many2one(
        'co.product.request', string='Source Product Request',
        readonly=True, copy=False)
```

Add the `estimated_amount` compute:

```python
    @api.depends('line_ids.subtotal')
    def _compute_estimated_amount(self):
        for rec in self:
            rec.estimated_amount = sum(rec.line_ids.mapped('subtotal'))
```

Add the `approval_state` compute:

```python
    @api.depends('approval_line_ids.state')
    def _compute_approval_state(self):
        for rec in self:
            lines = rec.approval_line_ids
            if not lines:
                rec.approval_state = 'no_approval'
            elif any(l.state == 'rejected' for l in lines):
                rec.approval_state = 'rejected'
            elif all(l.state == 'approved' for l in lines):
                rec.approval_state = 'approved'
            else:
                rec.approval_state = 'pending'
```

Modify the existing `action_submit` method to create approval lines:

```python
    def action_submit(self):
        for rec in self:
            if not rec.line_ids:
                raise UserError(_('Please add at least one product line.'))
            rec._create_approval_lines()
            if rec.approval_state in ('no_approval', 'approved'):
                rec.state = 'approved'
                rec.date_approved = fields.Date.today()
                rec.approver_id = self.env.user
            else:
                rec.state = 'submitted'
```

Add the method to create approval lines:

```python
    def _create_approval_lines(self):
        """Create approval lines based on configured levels."""
        self.ensure_one()
        self.approval_line_ids.unlink()
        ApprovalLevel = self.env['co.purchase.approval.level']
        amount = self.estimated_amount
        # Try department-specific levels first
        domain = [
            ('company_id', '=', self.company_id.id),
            ('department_id', '=', self.department_id.id),
            '|',
            ('max_amount', '=', 0),
            ('max_amount', '>=', amount),
            ('min_amount', '<=', amount),
        ]
        levels = ApprovalLevel.search(domain, order='sequence')
        if not levels and self.department_id:
            # Fall back to company-wide levels
            domain = [
                ('company_id', '=', self.company_id.id),
                ('department_id', '=', False),
                '|',
                ('max_amount', '=', 0),
                ('max_amount', '>=', amount),
                ('min_amount', '<=', amount),
            ]
            levels = ApprovalLevel.search(domain, order='sequence')
        for level in levels:
            self.env['co.purchase.approval.line'].create({
                'purchase_request_id': self.id,
                'approval_level_id': level.id,
            })
```

Add the approve/reject methods:

```python
    def action_approve(self):
        """Approve the current pending approval level."""
        self.ensure_one()
        pending = self.approval_line_ids.filtered(
            lambda l: l.state == 'pending')
        if not pending:
            raise UserError(_('No pending approval steps.'))
        current = pending.sorted('sequence')[0]
        if self.env.user not in current.approval_level_id.approver_ids:
            raise UserError(_(
                'You are not authorized to approve at level "%s".',
                current.approval_level_id.name))
        current.write({
            'state': 'approved',
            'approver_id': self.env.user.id,
            'date': fields.Datetime.now(),
        })
        if self.approval_state == 'approved':
            self.state = 'approved'
            self.date_approved = fields.Date.today()
            self.approver_id = self.env.user

    def action_reject(self):
        """Reject the current pending approval level."""
        self.ensure_one()
        pending = self.approval_line_ids.filtered(
            lambda l: l.state == 'pending')
        if not pending:
            raise UserError(_('No pending approval steps.'))
        current = pending.sorted('sequence')[0]
        if self.env.user not in current.approval_level_id.approver_ids:
            raise UserError(_(
                'You are not authorized to reject at level "%s".',
                current.approval_level_id.name))
        current.write({
            'state': 'rejected',
            'approver_id': self.env.user.id,
            'date': fields.Datetime.now(),
        })
        self.state = 'cancel'
```

Update the state field to add the new states — replace the existing `state` Selection:

```python
    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('approved', 'Approved'),
        ('rfq_sent', 'RFQs Sent'),
        ('quotation_compared', 'Quotations Compared'),
        ('purchase', 'Purchase Order Created'),
        ('done', 'Done'),
        ('cancel', 'Cancelled'),
    ], default='draft', tracking=True, string='Status')
```

- [ ] **Step 2: Update `views/co_purchase_request_views.xml`**

Add an approval timeline section to the form view. After the existing `line_ids` notebook page, add a new page:

```xml
<page string="Approval" name="approval"
      invisible="not approval_line_ids">
    <field name="approval_line_ids" readonly="1">
        <list>
            <field name="sequence"/>
            <field name="approval_level_id"/>
            <field name="state" widget="badge"
                   decoration-info="state == 'pending'"
                   decoration-success="state == 'approved'"
                   decoration-danger="state == 'rejected'"/>
            <field name="approver_id"/>
            <field name="date"/>
            <field name="notes"/>
        </list>
    </field>
</page>
```

Add the approval buttons to the header (replace existing Approve button):

```xml
<button name="action_approve"
        string="Approve"
        type="object"
        class="oe_highlight"
        invisible="state != 'submitted' or approval_state != 'pending'"/>
<button name="action_reject"
        string="Reject"
        type="object"
        class="btn-danger"
        invisible="state != 'submitted' or approval_state != 'pending'"/>
```

Add `estimated_amount`, `approval_state`, `supplier_count`, `product_request_id` fields to the form group section.

- [ ] **Step 3: Commit**

```bash
git add custom-addons/co_warehouse_extended/models/co_purchase_request.py \
        custom-addons/co_warehouse_extended/views/co_purchase_request_views.xml
git commit -m "feat: integrate N-level approval workflow into purchase requests"
```

---

## Task 6: Supplier Scoring Model

**Files:**
- Create: `custom-addons/co_warehouse_extended/models/co_supplier_score.py`
- Create: `custom-addons/co_warehouse_extended/views/co_supplier_score_views.xml`
- Modify: `custom-addons/co_warehouse_extended/models/__init__.py`
- Modify: `custom-addons/co_warehouse_extended/__manifest__.py`
- Modify: `custom-addons/co_warehouse_extended/views/co_menus.xml`

- [ ] **Step 1: Create `models/co_supplier_score.py`**

```python
from odoo import api, fields, models, _


class CoSupplierScore(models.Model):
    _name = 'co.supplier.score'
    _description = 'Supplier Score'
    _order = 'total_score desc'
    _rec_name = 'partner_id'

    partner_id = fields.Many2one(
        'res.partner', string='Supplier', required=True,
        domain="[('supplier_rank', '>', 0)]")
    product_category_id = fields.Many2one(
        'product.category', string='Product Category')
    company_id = fields.Many2one(
        'res.company', required=True,
        default=lambda self: self.env.company)
    score_price = fields.Float(string='Price Score (0-100)', default=50.0)
    score_delivery = fields.Float(string='Delivery Score (0-100)', default=50.0)
    score_quality = fields.Float(string='Quality Score (0-100)', default=50.0)
    score_compliance = fields.Float(string='Compliance Score (0-100)', default=50.0)
    weight_price = fields.Float(string='Price Weight')
    weight_delivery = fields.Float(string='Delivery Weight')
    weight_quality = fields.Float(string='Quality Weight')
    weight_compliance = fields.Float(string='Compliance Weight')
    total_score = fields.Float(
        string='Total Score', compute='_compute_total_score', store=True)
    last_updated = fields.Datetime(string='Last Recalculated')

    @api.depends('score_price', 'score_delivery', 'score_quality',
                 'score_compliance', 'weight_price', 'weight_delivery',
                 'weight_quality', 'weight_compliance')
    def _compute_total_score(self):
        for rec in self:
            total_weight = (rec.weight_price + rec.weight_delivery +
                            rec.weight_quality + rec.weight_compliance)
            if total_weight:
                rec.total_score = (
                    rec.score_price * rec.weight_price +
                    rec.score_delivery * rec.weight_delivery +
                    rec.score_quality * rec.weight_quality +
                    rec.score_compliance * rec.weight_compliance
                ) / total_weight
            else:
                rec.total_score = 0.0

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._apply_default_weights(vals)
        return super().create(vals_list)

    def _apply_default_weights(self, vals):
        """Apply company default weights if not provided."""
        company = self.env['res.company'].browse(
            vals.get('company_id', self.env.company.id))
        for field, default_field in [
            ('weight_price', 'supplier_weight_price'),
            ('weight_delivery', 'supplier_weight_delivery'),
            ('weight_quality', 'supplier_weight_quality'),
            ('weight_compliance', 'supplier_weight_compliance'),
        ]:
            if not vals.get(field):
                vals[field] = getattr(company, default_field)

    def action_recalculate(self):
        """Recalculate scores based on historical data."""
        for rec in self:
            rec._compute_price_score()
            rec._compute_delivery_score()
            rec._compute_quality_score()
            rec._compute_compliance_score()
            rec.last_updated = fields.Datetime.now()

    def _compute_price_score(self):
        """Score based on historical PO prices vs average."""
        self.ensure_one()
        domain = [
            ('order_id.partner_id', '=', self.partner_id.id),
            ('order_id.state', '=', 'purchase'),
            ('order_id.company_id', '=', self.company_id.id),
        ]
        if self.product_category_id:
            domain.append(
                ('product_id.categ_id', '=', self.product_category_id.id))
        lines = self.env['purchase.order.line'].search(domain, limit=100)
        if not lines:
            return
        avg_price = sum(lines.mapped('price_unit')) / len(lines)
        # Get average across all suppliers for same products
        all_domain = [
            ('order_id.state', '=', 'purchase'),
            ('order_id.company_id', '=', self.company_id.id),
            ('product_id', 'in', lines.mapped('product_id').ids),
        ]
        all_lines = self.env['purchase.order.line'].search(
            all_domain, limit=500)
        if not all_lines:
            return
        market_avg = sum(all_lines.mapped('price_unit')) / len(all_lines)
        if market_avg:
            # Lower price = higher score
            ratio = avg_price / market_avg
            self.score_price = max(0, min(100, (2 - ratio) * 50))

    def _compute_delivery_score(self):
        """Score based on on-time delivery rate."""
        self.ensure_one()
        pickings = self.env['stock.picking'].search([
            ('partner_id', '=', self.partner_id.id),
            ('picking_type_code', '=', 'incoming'),
            ('state', '=', 'done'),
            ('company_id', '=', self.company_id.id),
        ], limit=100)
        if not pickings:
            return
        on_time = sum(
            1 for p in pickings
            if p.date_done and p.scheduled_date and
            p.date_done <= p.scheduled_date)
        self.score_delivery = (on_time / len(pickings)) * 100

    def _compute_quality_score(self):
        """Score based on quality check pass rate."""
        self.ensure_one()
        pickings = self.env['stock.picking'].search([
            ('partner_id', '=', self.partner_id.id),
            ('picking_type_code', '=', 'incoming'),
            ('state', '=', 'done'),
            ('company_id', '=', self.company_id.id),
        ], limit=100)
        if not pickings:
            return
        passed = sum(1 for p in pickings if p.quality_check_passed)
        self.score_quality = (passed / len(pickings)) * 100

    def _compute_compliance_score(self):
        """Score based on order fulfillment rate."""
        self.ensure_one()
        orders = self.env['purchase.order'].search([
            ('partner_id', '=', self.partner_id.id),
            ('state', '=', 'purchase'),
            ('company_id', '=', self.company_id.id),
        ], limit=50)
        if not orders:
            return
        total_ordered = sum(orders.mapped('order_line.product_qty'))
        total_received = sum(orders.mapped('order_line.qty_received'))
        if total_ordered:
            self.score_compliance = min(
                100, (total_received / total_ordered) * 100)
```

- [ ] **Step 2: Create `views/co_supplier_score_views.xml`**

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="co_supplier_score_view_form" model="ir.ui.view">
        <field name="name">co.supplier.score.form</field>
        <field name="model">co.supplier.score</field>
        <field name="arch" type="xml">
            <form>
                <header>
                    <button name="action_recalculate"
                            string="Recalculate Scores"
                            type="object"
                            class="oe_highlight"/>
                </header>
                <sheet>
                    <group>
                        <group>
                            <field name="partner_id"/>
                            <field name="product_category_id"/>
                            <field name="company_id" groups="base.group_multi_company"/>
                        </group>
                        <group>
                            <field name="total_score" widget="progressbar"/>
                            <field name="last_updated"/>
                        </group>
                    </group>
                    <notebook>
                        <page string="Scores" name="scores">
                            <group>
                                <group string="Scores (0-100)">
                                    <field name="score_price"/>
                                    <field name="score_delivery"/>
                                    <field name="score_quality"/>
                                    <field name="score_compliance"/>
                                </group>
                                <group string="Weights">
                                    <field name="weight_price"/>
                                    <field name="weight_delivery"/>
                                    <field name="weight_quality"/>
                                    <field name="weight_compliance"/>
                                </group>
                            </group>
                        </page>
                    </notebook>
                </sheet>
            </form>
        </field>
    </record>

    <record id="co_supplier_score_view_list" model="ir.ui.view">
        <field name="name">co.supplier.score.list</field>
        <field name="model">co.supplier.score</field>
        <field name="arch" type="xml">
            <list>
                <field name="partner_id"/>
                <field name="product_category_id"/>
                <field name="score_price"/>
                <field name="score_delivery"/>
                <field name="score_quality"/>
                <field name="score_compliance"/>
                <field name="total_score" widget="progressbar"/>
                <field name="last_updated"/>
            </list>
        </field>
    </record>

    <record id="action_co_supplier_score" model="ir.actions.act_window">
        <field name="name">Supplier Scores</field>
        <field name="res_model">co.supplier.score</field>
        <field name="view_mode">list,form</field>
        <field name="path">supplier-scores</field>
        <field name="help" type="html">
            <p class="o_view_nocontent_smiling_face">
                No supplier scores yet
            </p>
            <p>Supplier scores are created when evaluating suppliers
               for purchase requests. You can also create them manually.</p>
        </field>
    </record>
</odoo>
```

- [ ] **Step 3: Update `models/__init__.py`**

Add:

```python
from . import co_supplier_score
```

- [ ] **Step 4: Update `__manifest__.py`**

Add to `data` list:

```python
'views/co_supplier_score_views.xml',
```

- [ ] **Step 5: Update `views/co_menus.xml`**

Add under Purchase menu:

```xml
    <menuitem id="menu_supplier_scores"
              name="Supplier Scores"
              parent="purchase.menu_purchase_root"
              action="action_co_supplier_score"
              sequence="25"/>
```

- [ ] **Step 6: Commit**

```bash
git add custom-addons/co_warehouse_extended/models/co_supplier_score.py \
        custom-addons/co_warehouse_extended/views/co_supplier_score_views.xml \
        custom-addons/co_warehouse_extended/models/__init__.py \
        custom-addons/co_warehouse_extended/__manifest__.py \
        custom-addons/co_warehouse_extended/views/co_menus.xml
git commit -m "feat: add multi-criteria supplier scoring model"
```

---

## Task 7: Quotation Comparison Model

**Files:**
- Create: `custom-addons/co_warehouse_extended/models/co_quotation_comparison.py`
- Create: `custom-addons/co_warehouse_extended/views/co_quotation_comparison_views.xml`
- Modify: `custom-addons/co_warehouse_extended/models/__init__.py`
- Modify: `custom-addons/co_warehouse_extended/__manifest__.py`
- Modify: `custom-addons/co_warehouse_extended/views/co_menus.xml`

- [ ] **Step 1: Create `models/co_quotation_comparison.py`**

```python
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class CoQuotationComparison(models.Model):
    _name = 'co.quotation.comparison'
    _description = 'Quotation Comparison'
    _order = 'create_date desc'

    purchase_request_id = fields.Many2one(
        'co.purchase.request', string='Purchase Request',
        required=True, ondelete='cascade')
    rfq_ids = fields.One2many(
        'purchase.order', 'co_comparison_id', string='RFQs')
    recommended_rfq_id = fields.Many2one(
        'purchase.order', string='Recommended',
        compute='_compute_recommended', store=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('compared', 'Compared'),
        ('selected', 'Selected'),
    ], default='draft', string='Status')
    selected_rfq_id = fields.Many2one(
        'purchase.order', string='Selected RFQ', readonly=True)

    @api.depends('rfq_ids.amount_total', 'rfq_ids.partner_id')
    def _compute_recommended(self):
        for rec in self:
            if not rec.rfq_ids:
                rec.recommended_rfq_id = False
                continue
            best = None
            best_score = -1
            for rfq in rec.rfq_ids:
                # Find supplier score
                supplier_score = self.env['co.supplier.score'].search([
                    ('partner_id', '=', rfq.partner_id.id),
                    ('company_id', '=', rfq.company_id.id),
                ], limit=1)
                score = supplier_score.total_score if supplier_score else 50.0
                # Combine: higher supplier score + lower price = better
                # Normalize price inversely (lower is better)
                max_total = max(r.amount_total for r in rec.rfq_ids) or 1
                price_score = (1 - rfq.amount_total / max_total) * 100 if max_total else 50
                combined = score * 0.6 + price_score * 0.4
                if combined > best_score:
                    best_score = combined
                    best = rfq
            rec.recommended_rfq_id = best

    def action_accept_recommendation(self):
        """Accept the recommended RFQ and cancel others."""
        self.ensure_one()
        if not self.recommended_rfq_id:
            raise UserError(_('No recommendation available.'))
        self._select_rfq(self.recommended_rfq_id)

    def action_select_rfq(self):
        """Open wizard or directly select an RFQ (called from button with context)."""
        self.ensure_one()
        rfq_id = self.env.context.get('selected_rfq_id')
        if rfq_id:
            rfq = self.env['purchase.order'].browse(rfq_id)
            self._select_rfq(rfq)
        return True

    def _select_rfq(self, rfq):
        """Confirm selected RFQ, cancel others, create PO."""
        self.ensure_one()
        for other in self.rfq_ids - rfq:
            other.button_cancel()
        rfq.button_confirm()
        self.selected_rfq_id = rfq.id
        self.state = 'selected'
        # Update the purchase request
        self.purchase_request_id.write({
            'state': 'purchase',
        })
```

- [ ] **Step 2: Add `co_comparison_id` to `purchase.order` in `stock_picking.py`**

In the existing `PurchaseOrder` class in `models/stock_picking.py`, add:

```python
    co_comparison_id = fields.Many2one(
        'co.quotation.comparison', string='Quotation Comparison',
        readonly=True, copy=False)
```

- [ ] **Step 3: Create `views/co_quotation_comparison_views.xml`**

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="co_quotation_comparison_view_form" model="ir.ui.view">
        <field name="name">co.quotation.comparison.form</field>
        <field name="model">co.quotation.comparison</field>
        <field name="arch" type="xml">
            <form>
                <header>
                    <button name="action_accept_recommendation"
                            string="Accept Recommendation"
                            type="object"
                            class="oe_highlight"
                            invisible="state != 'draft'"/>
                    <field name="state" widget="statusbar"/>
                </header>
                <sheet>
                    <group>
                        <group>
                            <field name="purchase_request_id"/>
                            <field name="recommended_rfq_id"/>
                        </group>
                        <group>
                            <field name="selected_rfq_id"
                                   invisible="state != 'selected'"/>
                        </group>
                    </group>
                    <notebook>
                        <page string="Quotations" name="quotations">
                            <field name="rfq_ids" readonly="1">
                                <list decoration-success="id == parent.recommended_rfq_id">
                                    <field name="partner_id"/>
                                    <field name="amount_total"/>
                                    <field name="date_order"/>
                                    <field name="state" widget="badge"/>
                                    <button name="%(co_warehouse_extended.action_co_quotation_comparison)d"
                                            string="Select"
                                            type="action"
                                            context="{'selected_rfq_id': id}"
                                            invisible="parent.state == 'selected'"
                                            class="btn-link"/>
                                </list>
                            </field>
                        </page>
                    </notebook>
                </sheet>
            </form>
        </field>
    </record>

    <record id="co_quotation_comparison_view_list" model="ir.ui.view">
        <field name="name">co.quotation.comparison.list</field>
        <field name="model">co.quotation.comparison</field>
        <field name="arch" type="xml">
            <list>
                <field name="purchase_request_id"/>
                <field name="recommended_rfq_id"/>
                <field name="selected_rfq_id"/>
                <field name="state" widget="badge"/>
            </list>
        </field>
    </record>

    <record id="action_co_quotation_comparison" model="ir.actions.act_window">
        <field name="name">Quotation Comparisons</field>
        <field name="res_model">co.quotation.comparison</field>
        <field name="view_mode">list,form</field>
        <field name="path">quotation-comparisons</field>
    </record>
</odoo>
```

- [ ] **Step 4: Update `models/__init__.py`**

Add:

```python
from . import co_quotation_comparison
```

- [ ] **Step 5: Update `__manifest__.py`**

Add to `data` list:

```python
'views/co_quotation_comparison_views.xml',
```

- [ ] **Step 6: Update `views/co_menus.xml`**

Add:

```xml
    <menuitem id="menu_quotation_comparison"
              name="Quotation Comparisons"
              parent="purchase.menu_purchase_root"
              action="action_co_quotation_comparison"
              sequence="20"/>
```

- [ ] **Step 7: Commit**

```bash
git add custom-addons/co_warehouse_extended/models/co_quotation_comparison.py \
        custom-addons/co_warehouse_extended/views/co_quotation_comparison_views.xml \
        custom-addons/co_warehouse_extended/models/stock_picking.py \
        custom-addons/co_warehouse_extended/models/__init__.py \
        custom-addons/co_warehouse_extended/__manifest__.py \
        custom-addons/co_warehouse_extended/views/co_menus.xml
git commit -m "feat: add quotation comparison model with recommendation engine"
```

---

## Task 8: Supplier Evaluation & RFQ Creation on Purchase Request

**Files:**
- Modify: `custom-addons/co_warehouse_extended/models/co_purchase_request.py`

- [ ] **Step 1: Add RFQ creation methods to `co_purchase_request.py`**

Add after the approval methods:

```python
    def action_request_quotations(self):
        """Score suppliers and create RFQs for top N suppliers."""
        self.ensure_one()
        if self.state != 'approved':
            raise UserError(_('Purchase request must be approved first.'))

        supplier_count = self.supplier_count or self.company_id.default_supplier_count or 3

        # Collect all products from lines
        products = self.line_ids.mapped('product_id')

        # Find suppliers who sell these products
        supplier_ids = set()
        for product in products:
            for seller in product.seller_ids:
                supplier_ids.add(seller.partner_id.id)

        # Also include explicitly assigned suppliers on lines
        for line in self.line_ids:
            if line.supplier_id:
                supplier_ids.add(line.supplier_id.id)

        if not supplier_ids:
            raise UserError(_(
                'No suppliers found for the requested products. '
                'Please configure supplier info on the products.'))

        # Get or create supplier scores and rank
        scored_suppliers = []
        SupplierScore = self.env['co.supplier.score']
        for partner_id in supplier_ids:
            score_rec = SupplierScore.search([
                ('partner_id', '=', partner_id),
                ('company_id', '=', self.company_id.id),
            ], limit=1)
            if not score_rec:
                score_rec = SupplierScore.create({
                    'partner_id': partner_id,
                    'company_id': self.company_id.id,
                })
                score_rec.action_recalculate()
            scored_suppliers.append((score_rec.total_score, partner_id))

        # Sort by score descending, take top N
        scored_suppliers.sort(key=lambda x: x[0], reverse=True)
        top_suppliers = scored_suppliers[:supplier_count]

        # Create comparison record
        comparison = self.env['co.quotation.comparison'].create({
            'purchase_request_id': self.id,
        })
        self.comparison_id = comparison.id

        # Create one RFQ per top supplier
        for _score, partner_id in top_suppliers:
            po_vals = {
                'partner_id': partner_id,
                'company_id': self.company_id.id,
                'origin': self.name,
                'co_purchase_request_id': self.id,
                'co_comparison_id': comparison.id,
                'order_line': [(0, 0, {
                    'product_id': line.product_id.id,
                    'product_qty': line.quantity,
                    'price_unit': line.estimated_price,
                    'name': line.product_id.display_name,
                    'product_uom': line.product_uom_id.id,
                    'date_planned': fields.Datetime.now(),
                }) for line in self.line_ids],
            }
            self.env['purchase.order'].create(po_vals)

        self.state = 'rfq_sent'
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'co.quotation.comparison',
            'view_mode': 'form',
            'res_id': comparison.id,
        }

    def action_view_comparison(self):
        """View the quotation comparison."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'co.quotation.comparison',
            'view_mode': 'form',
            'res_id': self.comparison_id.id,
        }
```

- [ ] **Step 2: Add RFQ button to purchase request form view**

In `views/co_purchase_request_views.xml`, add to header buttons:

```xml
<button name="action_request_quotations"
        string="Request Quotations"
        type="object"
        class="oe_highlight"
        invisible="state != 'approved'"/>
<button name="action_view_comparison"
        string="View Comparisons"
        type="object"
        invisible="not comparison_id"
        class="oe_stat_button"
        icon="fa-balance-scale"/>
```

Add `supplier_count` to the form:

```xml
<field name="supplier_count"
       invisible="state not in ('draft', 'submitted', 'approved')"
       placeholder="Use company default"/>
```

- [ ] **Step 3: Commit**

```bash
git add custom-addons/co_warehouse_extended/models/co_purchase_request.py \
        custom-addons/co_warehouse_extended/views/co_purchase_request_views.xml
git commit -m "feat: add supplier evaluation and RFQ creation to purchase request"
```

---

## Task 9: PO Fulfillment Tracking & Journal Entries on Receipt

**Files:**
- Modify: `custom-addons/co_warehouse_extended/models/stock_picking.py`

- [ ] **Step 1: Add fulfillment tracking to `PurchaseOrder` class**

In the existing `PurchaseOrder` class in `models/stock_picking.py`, add:

```python
    co_fulfillment_pct = fields.Float(
        string='Fulfillment %',
        compute='_compute_fulfillment', store=True)
    co_fulfillment_state = fields.Selection([
        ('pending', 'Pending'),
        ('partial', 'Partial'),
        ('complete', 'Complete'),
    ], string='Fulfillment Status',
        compute='_compute_fulfillment', store=True)

    @api.depends('order_line.product_qty', 'order_line.qty_received')
    def _compute_fulfillment(self):
        for order in self:
            total_qty = sum(order.order_line.mapped('product_qty'))
            received_qty = sum(order.order_line.mapped('qty_received'))
            if total_qty:
                order.co_fulfillment_pct = (received_qty / total_qty) * 100
            else:
                order.co_fulfillment_pct = 0.0
            if received_qty == 0:
                order.co_fulfillment_state = 'pending'
            elif received_qty >= total_qty:
                order.co_fulfillment_state = 'complete'
            else:
                order.co_fulfillment_state = 'partial'
```

- [ ] **Step 2: Add journal entry generation to `StockPicking.button_validate`**

Replace the existing `button_validate` method in the `StockPicking` class:

```python
    def button_validate(self):
        res = super().button_validate()
        for picking in self:
            if picking.state != 'done':
                continue
            if picking.picking_type_code != 'incoming':
                continue
            if not picking.purchase_id:
                continue
            journal_mode = picking.company_id.purchase_journal_mode
            if journal_mode == 'auto_entry':
                picking._create_receipt_journal_entry()
            elif picking.co_auto_invoice and not picking.co_invoice_id:
                picking._create_vendor_bill()
        return res

    def _create_receipt_journal_entry(self):
        """Create journal entry for goods receipt: debit inventory, credit payable."""
        self.ensure_one()
        journal = self.env['account.journal'].search([
            ('type', '=', 'general'),
            ('company_id', '=', self.company_id.id),
        ], limit=1)
        if not journal:
            return

        move_lines = []
        for move in self.move_ids.filtered(lambda m: m.state == 'done'):
            product = move.product_id
            qty = move.quantity
            price = product.standard_price
            amount = qty * price

            if amount == 0:
                continue

            # Inventory account (debit)
            stock_account = (
                product.categ_id.property_stock_valuation_account_id or
                product.categ_id.property_stock_account_input_categ_id)
            # Payable account (credit)
            payable_account = self.partner_id.property_account_payable_id

            if not stock_account or not payable_account:
                continue

            move_lines.append((0, 0, {
                'name': _('%s - Receipt', product.display_name),
                'account_id': stock_account.id,
                'debit': amount,
                'credit': 0.0,
                'product_id': product.id,
                'quantity': qty,
            }))
            move_lines.append((0, 0, {
                'name': _('%s - Payable', product.display_name),
                'account_id': payable_account.id,
                'debit': 0.0,
                'credit': amount,
                'partner_id': self.partner_id.id,
            }))

            # Tax lines
            if product.supplier_taxes_id:
                taxes = product.supplier_taxes_id.compute_all(
                    price, currency=self.company_id.currency_id,
                    quantity=qty, product=product, partner=self.partner_id)
                for tax_line in taxes.get('taxes', []):
                    tax_amount = tax_line['amount']
                    if tax_amount:
                        tax_account = tax_line.get('account_id')
                        if tax_account:
                            # Adjust payable credit by tax
                            move_lines.append((0, 0, {
                                'name': tax_line['name'],
                                'account_id': tax_account,
                                'debit': abs(tax_amount) if tax_amount > 0 else 0,
                                'credit': abs(tax_amount) if tax_amount < 0 else 0,
                            }))
                            # Increase payable for tax
                            move_lines.append((0, 0, {
                                'name': _('Tax payable - %s', tax_line['name']),
                                'account_id': payable_account.id,
                                'debit': 0.0,
                                'credit': abs(tax_amount) if tax_amount > 0 else 0,
                            }))

        if not move_lines:
            return

        account_move = self.env['account.move'].create({
            'journal_id': journal.id,
            'date': fields.Date.today(),
            'ref': _('Receipt: %s', self.name),
            'move_type': 'entry',
            'line_ids': move_lines,
        })
        account_move.action_post()
        self.co_invoice_id = account_move.id
```

- [ ] **Step 3: Add fulfillment fields to PO form view**

In `views/purchase_order_views.xml`, add to the inherited view:

```xml
<xpath expr="//field[@name='co_purchase_request_id']" position="after">
    <field name="co_fulfillment_pct" widget="progressbar"/>
    <field name="co_fulfillment_state" widget="badge"
           decoration-warning="co_fulfillment_state == 'partial'"
           decoration-success="co_fulfillment_state == 'complete'"/>
</xpath>
```

- [ ] **Step 4: Commit**

```bash
git add custom-addons/co_warehouse_extended/models/stock_picking.py \
        custom-addons/co_warehouse_extended/views/purchase_order_views.xml
git commit -m "feat: add PO fulfillment tracking and automatic journal entries on receipt"
```

---

## Task 10: Approval Level Views & Configuration

**Files:**
- Create: `custom-addons/co_warehouse_extended/views/co_purchase_approval_level_views.xml`
- Modify: `custom-addons/co_warehouse_extended/__manifest__.py`
- Modify: `custom-addons/co_warehouse_extended/views/co_menus.xml`

- [ ] **Step 1: Create `views/co_purchase_approval_level_views.xml`**

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="co_purchase_approval_level_view_form" model="ir.ui.view">
        <field name="name">co.purchase.approval.level.form</field>
        <field name="model">co.purchase.approval.level</field>
        <field name="arch" type="xml">
            <form>
                <sheet>
                    <group>
                        <group>
                            <field name="name"/>
                            <field name="company_id" groups="base.group_multi_company"/>
                            <field name="department_id"/>
                            <field name="sequence"/>
                        </group>
                        <group>
                            <field name="min_amount"/>
                            <field name="max_amount"/>
                            <field name="currency_id"/>
                        </group>
                    </group>
                    <group string="Authorized Approvers">
                        <field name="approver_ids" widget="many2many_tags"
                               nolabel="1"/>
                    </group>
                </sheet>
            </form>
        </field>
    </record>

    <record id="co_purchase_approval_level_view_list" model="ir.ui.view">
        <field name="name">co.purchase.approval.level.list</field>
        <field name="model">co.purchase.approval.level</field>
        <field name="arch" type="xml">
            <list>
                <field name="sequence" widget="handle"/>
                <field name="name"/>
                <field name="department_id"/>
                <field name="min_amount"/>
                <field name="max_amount"/>
                <field name="currency_id"/>
                <field name="approver_ids" widget="many2many_tags"/>
                <field name="company_id" groups="base.group_multi_company"/>
            </list>
        </field>
    </record>

    <record id="action_co_purchase_approval_level" model="ir.actions.act_window">
        <field name="name">Approval Levels</field>
        <field name="res_model">co.purchase.approval.level</field>
        <field name="view_mode">list,form</field>
        <field name="path">purchase-approval-levels</field>
        <field name="help" type="html">
            <p class="o_view_nocontent_smiling_face">
                Configure purchase approval levels
            </p>
            <p>Define amount-based approval tiers per department or company.
               If no levels match a request's amount, it will be auto-approved.</p>
        </field>
    </record>
</odoo>
```

- [ ] **Step 2: Update `__manifest__.py`**

Add to `data` list:

```python
'views/co_purchase_approval_level_views.xml',
```

- [ ] **Step 3: Update `views/co_menus.xml`**

Add a configuration submenu under Purchase:

```xml
    <menuitem id="menu_purchase_workflow_config"
              name="Purchase Workflow"
              parent="purchase.menu_purchase_config"
              sequence="50"/>
    <menuitem id="menu_purchase_approval_levels"
              name="Approval Levels"
              parent="menu_purchase_workflow_config"
              action="action_co_purchase_approval_level"
              groups="co_warehouse_extended.group_purchase_request_manager"
              sequence="10"/>
```

- [ ] **Step 4: Commit**

```bash
git add custom-addons/co_warehouse_extended/views/co_purchase_approval_level_views.xml \
        custom-addons/co_warehouse_extended/__manifest__.py \
        custom-addons/co_warehouse_extended/views/co_menus.xml
git commit -m "feat: add approval level configuration views and menus"
```

---

## Task 11: Security Rules for New Models

**Files:**
- Modify: `custom-addons/co_warehouse_extended/security/co_warehouse_security.xml`
- Modify: `custom-addons/co_warehouse_extended/security/ir.model.access.csv`

- [ ] **Step 1: Add approver group to `co_warehouse_security.xml`**

Add after the existing `group_purchase_request_manager`:

```xml
<record id="group_purchase_approver" model="res.groups">
    <field name="name">Purchase Approver</field>
    <field name="category_id" ref="module_category_co_warehouse"/>
    <field name="implied_ids" eval="[(4, ref('group_purchase_request_user'))]"/>
</record>
```

- [ ] **Step 2: Add access rules to `ir.model.access.csv`**

Append these rows:

```csv
access_co_product_request_user,co.product.request user,model_co_product_request,group_purchase_request_user,1,1,1,0
access_co_product_request_manager,co.product.request manager,model_co_product_request,group_purchase_request_manager,1,1,1,1
access_co_product_request_line_user,co.product.request.line user,model_co_product_request_line,group_purchase_request_user,1,1,1,0
access_co_product_request_line_manager,co.product.request.line manager,model_co_product_request_line,group_purchase_request_manager,1,1,1,1
access_co_purchase_approval_level_user,co.purchase.approval.level user,model_co_purchase_approval_level,group_purchase_request_user,1,0,0,0
access_co_purchase_approval_level_manager,co.purchase.approval.level manager,model_co_purchase_approval_level,group_purchase_request_manager,1,1,1,1
access_co_purchase_approval_line_user,co.purchase.approval.line user,model_co_purchase_approval_line,group_purchase_request_user,1,0,0,0
access_co_purchase_approval_line_manager,co.purchase.approval.line manager,model_co_purchase_approval_line,group_purchase_request_manager,1,1,1,1
access_co_supplier_score_user,co.supplier.score user,model_co_supplier_score,group_purchase_request_user,1,0,0,0
access_co_supplier_score_manager,co.supplier.score manager,model_co_supplier_score,group_purchase_request_manager,1,1,1,1
access_co_quotation_comparison_user,co.quotation.comparison user,model_co_quotation_comparison,group_purchase_request_user,1,0,0,0
access_co_quotation_comparison_manager,co.quotation.comparison manager,model_co_quotation_comparison,group_purchase_request_manager,1,1,1,1
```

- [ ] **Step 3: Commit**

```bash
git add custom-addons/co_warehouse_extended/security/co_warehouse_security.xml \
        custom-addons/co_warehouse_extended/security/ir.model.access.csv
git commit -m "feat: add security groups and access rules for purchase workflow models"
```

---

## Task 12: Update Manifest with All New Files & Upgrade Module

**Files:**
- Modify: `custom-addons/co_warehouse_extended/__manifest__.py`

- [ ] **Step 1: Verify final `__manifest__.py` data list**

The complete `data` list should be (in order):

```python
'data': [
    'security/co_warehouse_security.xml',
    'security/ir.model.access.csv',
    'data/sequences.xml',
    'data/product_request_sequence.xml',
    'views/co_product_request_views.xml',
    'views/co_purchase_request_views.xml',
    'views/co_purchase_approval_level_views.xml',
    'views/co_inventory_formula_views.xml',
    'views/co_supplier_score_views.xml',
    'views/co_quotation_comparison_views.xml',
    'views/stock_warehouse_views.xml',
    'views/stock_warehouse_orderpoint_views.xml',
    'views/stock_picking_views.xml',
    'views/purchase_order_views.xml',
    'views/res_config_settings_views.xml',
    'views/co_menus.xml',
    'wizard/co_warehouse_transfer_wizard_views.xml',
],
```

The `depends` list should be:

```python
'depends': ['stock', 'purchase', 'purchase_requisition', 'account', 'mail', 'hr'],
```

The `models/__init__.py` complete imports:

```python
from . import co_purchase_request
from . import co_purchase_request_line
from . import co_product_request
from . import co_product_request_line
from . import co_purchase_approval_level
from . import co_purchase_approval_line
from . import co_supplier_score
from . import co_quotation_comparison
from . import co_inventory_formula
from . import res_company
from . import res_config_settings
from . import stock_warehouse
from . import stock_warehouse_orderpoint
from . import stock_picking
```

- [ ] **Step 2: Upgrade the module**

```bash
docker compose exec odoo odoo -u co_warehouse_extended -d odoo-club19 --stop-after-init
```

Expected: Module upgrades without errors. Watch for: missing field references, XML ID conflicts, access rule errors.

- [ ] **Step 3: Commit any fixes**

```bash
git add -u custom-addons/co_warehouse_extended/
git commit -m "fix: finalize manifest and fix any upgrade issues"
```

---

## Task 13: Browser Testing — Full Workflow

**Files:** None (testing only)

- [ ] **Step 1: Ensure Docker containers are running**

```bash
docker compose up -d
```

Wait for Odoo to be accessible at http://localhost:8069.

- [ ] **Step 2: Test Product Request creation**

Using Chrome browser tools:
1. Log in to Odoo at localhost:8069
2. Navigate to Purchase → Product Requests
3. Create a new product request with 2-3 products
4. Verify form fields: requester, department, warehouse, product lines
5. Click "Check Availability" — verify lines show availability status

- [ ] **Step 3: Test stock split behavior**

1. If items are partially/fully available, verify split quantities are shown
2. For auto mode: verify it processes automatically
3. For manual mode: verify user can adjust split quantities and confirm

- [ ] **Step 4: Test purchase request generation**

1. After processing, click the Purchase Request stat button
2. Verify purchase request was created with correct lines and amounts
3. Verify the estimated_amount is computed correctly

- [ ] **Step 5: Test approval workflow**

1. Navigate to Configuration → Purchase Workflow → Approval Levels
2. Create approval levels (e.g., 0-5000 Manager, 5001+ Director)
3. Create a new purchase request manually or via product request
4. Submit it and verify approval lines are created
5. Log in as approver and approve
6. Verify state transitions correctly

- [ ] **Step 6: Test supplier scoring and RFQ creation**

1. Navigate to Supplier Scores, create/recalculate some scores
2. On an approved purchase request, click "Request Quotations"
3. Verify RFQs are created for top N suppliers
4. Verify quotation comparison view shows all RFQs

- [ ] **Step 7: Test quotation comparison and PO creation**

1. Open the quotation comparison
2. Verify recommendation is highlighted
3. Click "Accept Recommendation" or select manually
4. Verify PO is confirmed and other RFQs cancelled

- [ ] **Step 8: Test receipt and journal entry**

1. On the confirmed PO, process a receipt (full or partial)
2. Verify fulfillment percentage updates
3. Verify journal entry is created (or vendor bill, depending on config)
4. Verify inventory stock is updated

- [ ] **Step 9: Fix any bugs found and re-test**

Iterate: fix bugs → upgrade module → re-test until all steps pass.
