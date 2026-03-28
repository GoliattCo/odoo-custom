# Account Product Category Accounts — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a small Odoo 18 module that makes the Income Account and Expense Account fields visible on the product.category form for all internal users by removing the `account.group_account_readonly` restriction from the existing view.

**Architecture:** Single view-only module. Inherits `account.view_category_property_form` (the view that already adds Income/Expense account fields to product.category) and removes the `groups` attribute restriction so the fields are visible regardless of accounting permissions.

**Tech Stack:** Odoo 18, XML view inheritance only. No Python.

---

## Chunk 1: Module scaffold and view override

### Task 1: Create the module directory and manifest

**Files:**
- Create: `custom-addons/account_product_category_accounts/__manifest__.py`
- Create: `custom-addons/account_product_category_accounts/__init__.py`

- [ ] **Step 1: Create `__init__.py` (empty)**

  File: `custom-addons/account_product_category_accounts/__init__.py`
  ```python
  ```
  (empty file)

- [ ] **Step 2: Create `__manifest__.py`**

  File: `custom-addons/account_product_category_accounts/__manifest__.py`
  ```python
  {
      'name': 'Account Product Category Accounts',
      'version': '18.0.1.0.0',
      'summary': 'Show income/expense accounts on product categories for all internal users',
      'category': 'Accounting',
      'depends': ['account', 'product'],
      'data': ['views/product_category_views.xml'],
      'installable': True,
      'auto_install': False,
      'license': 'LGPL-3',
  }
  ```

- [ ] **Step 3: Commit scaffold**

  ```bash
  cd /Users/manuelcaro/Odoo
  git add custom-addons/account_product_category_accounts/
  git commit -m "feat(account_product_category_accounts): add module scaffold"
  ```

---

### Task 2: Create the view override

**Files:**
- Create: `custom-addons/account_product_category_accounts/views/product_category_views.xml`

**Background:** The `account` module already adds `property_account_income_categ_id` and `property_account_expense_categ_id` to the product.category form via `account.view_category_property_form`. That view wraps both fields in a group with `groups="account.group_account_readonly"`, hiding them from users without accounting access. We inherit that view and clear the `groups` attribute.

- [ ] **Step 1: Create the views directory and XML file**

  File: `custom-addons/account_product_category_accounts/views/product_category_views.xml`
  ```xml
  <?xml version="1.0" encoding="utf-8"?>
  <odoo>
      <record id="view_category_accounts_visible" model="ir.ui.view">
          <field name="name">product.category.accounts.visible</field>
          <field name="model">product.category</field>
          <field name="inherit_id" ref="account.view_category_property_form"/>
          <field name="arch" type="xml">
              <xpath expr="//group[@name='account_property']/group" position="attributes">
                  <attribute name="groups"/>
              </xpath>
          </field>
      </record>
  </odoo>
  ```

  **How it works:** We inherit `account.view_category_property_form` (the view that adds the fields in the first place) rather than the base product.category form — inheriting the base view would add duplicate fields. The `xpath` targets the inner group by navigating through the stable outer `name="account_property"` attribute, making the selector robust to string label changes. `<attribute name="groups"/>` sets the `groups` attribute to empty string, which Odoo treats as "no restriction" — visible to all internal users.

- [ ] **Step 2: Commit view**

  ```bash
  cd /Users/manuelcaro/Odoo
  git add custom-addons/account_product_category_accounts/views/
  git commit -m "feat(account_product_category_accounts): add view override to show account fields"
  ```

---

### Task 3: Install and verify

- [ ] **Step 1: Restart Odoo to pick up the new module**

  ```bash
  cd /Users/manuelcaro/Odoo
  docker compose restart odoo
  ```

  Wait ~15 seconds, then confirm it's up:
  ```bash
  docker compose logs odoo --tail=5
  ```
  Expected: last line shows `HTTP service (werkzeug) running on` or similar — no tracebacks.

- [ ] **Step 2: Install the module**

  In the browser:
  1. Go to **Settings → Apps** (enable developer mode first if needed: add `?debug=1` to any URL)
  2. Search for `account_product_category_accounts`
  3. Click **Install**

  Alternatively via CLI:
  ```bash
  docker compose exec odoo odoo --stop-after-init -d odoo -i account_product_category_accounts
  ```
  Then restart: `docker compose restart odoo`

- [ ] **Step 3: Verify fields are visible**

  1. Go to **Inventory → Configuration → Product Categories** (or **Settings → Technical → Product Categories** with developer mode on)
  2. Open any product category (e.g., **All**)
  3. Confirm you see the **"Account Properties"** group with:
     - **Income Account** dropdown
     - **Expense Account** dropdown
  4. Confirm the dropdowns are searchable `account.account` Many2one fields (type a few letters and see matching accounts)

- [ ] **Step 4: Confirm success or diagnose failure**

  If fields are visible: implementation is complete.

  If fields are still hidden, check for a view inheritance error:
  ```bash
  docker compose logs odoo 2>&1 | grep -i "account_product_category_accounts\|view_category_accounts_visible"
  ```
  A failing xpath will log a warning at module install time. If you see one, re-check that the outer group `name="account_property"` still exists in the installed Odoo version with:
  ```bash
  grep -n "account_property" /Users/manuelcaro/Odoo/odoo/addons/account/views/product_view.xml
  ```
