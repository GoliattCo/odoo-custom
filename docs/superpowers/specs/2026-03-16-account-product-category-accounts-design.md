---
title: account_product_category_accounts — Design Spec
date: 2026-03-16
status: approved
---

# account_product_category_accounts

## Goal

Surface the two existing `account.account` fields on the `product.category` form view so users can assign a Sales (Income) account and a Purchase (Expense) account per product category.

## Context

Odoo 18's `account` module already adds `property_account_income_categ_id` and `property_account_expense_categ_id` to the `product.category` model, but these fields are not visible in the default form view at `/odoo/action-201`. This module makes them visible with no model changes.

## Approach

Minimal view-only module. No Python, no new fields, no migrations.

## Module Structure

```
custom-addons/account_product_category_accounts/
├── __manifest__.py
├── __init__.py
└── views/
    └── product_category_views.xml
```

## Manifest

- **name:** Account Product Category Accounts
- **version:** 18.0.1.0.0
- **depends:** `['account', 'product']`
- **data:** `['views/product_category_views.xml']`

## View

Inherits `account.view_category_property_form` — the view added by the `account` module that already places both fields inside a group with `groups="account.group_account_readonly"`.

**Why not inherit the base view?** The fields are already declared in `account.view_category_property_form`. Inheriting `product.product_category_form_view` directly and re-declaring the fields would render them twice.

Uses an `xpath` targeting the outer group's stable `name="account_property"` attribute to locate the inner group and clear its `groups` restriction:

```xml
<xpath expr="//group[@name='account_property']/group" position="attributes">
    <attribute name="groups"/>
</xpath>
```

Setting `groups` to empty string removes the restriction — fields become visible to all internal users. Both fields (`property_account_income_categ_id`, `property_account_expense_categ_id`) render as searchable `account.account` Many2one dropdowns, identical to the account selector on the Taxes form.

## Out of Scope

- No Python model changes
- No access rules (fields already secured by `account` module)
- No translations (field labels inherited from `account` module)
