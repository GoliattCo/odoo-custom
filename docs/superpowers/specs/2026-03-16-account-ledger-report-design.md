---
title: account_ledger_report — Design Spec
date: 2026-03-16
status: approved
---

# account_ledger_report

## Goal

A new standalone Odoo 18 module that provides a live account ledger report showing all posted journal entry lines with their debits, credits, date, account, and partner. Supports screen (list + pivot), PDF, and Excel export.

## Module

**Name:** `account_ledger_report`
**Depends:** `['account']`

## Data Model

Model: `account.ledger.report`
- `_auto = False` — backed by a SQL view, not a real table
- `_order = 'date desc'`
- Read-only (no create/write/unlink)

Only **posted** journal entries are included (`parent_state = 'posted'`).

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `date` | Date | Entry date from `account_move.date` |
| `account_id` | Many2one(account.account) | The ledger account |
| `account_code` | Char | Account code — populated from SQL SELECT directly (not ORM related) |
| `move_id` | Many2one(account.move) | The journal entry / invoice |
| `move_name` | Char | Journal entry reference — populated from SQL SELECT directly (not ORM related) |
| `partner_id` | Many2one(res.partner) | Customer or vendor |
| `debit` | Monetary | Debit amount |
| `credit` | Monetary | Credit amount |
| `company_id` | Many2one(res.company) | Company (for multi-company) |
| `currency_id` | Many2one(res.currency) | Company currency (for monetary fields) |

### SQL

`_table_query` property returns a SQL SELECT from `account_move_line` joined with `account_move` on `move_id`, filtered to `parent_state = 'posted'`.

## Views

### List View

Columns: Date · Account Code · Account · Reference · Partner · Debit · Credit
Aggregators: `sum` on Debit and Credit columns.
Includes a **"Print PDF"** button that triggers the QWeb report action on the **selected records**. To print all filtered records, the user selects all rows first (standard Odoo list behavior).

### Pivot View

Default configuration:
- Rows: `account_id`
- Measures: Debit, Credit

### Search View

| Filter/Field | Type | Domain |
|---|---|---|
| Start Date | date filter | `[('date', '>=', value)]` |
| End Date | date filter | `[('date', '<=', value)]` |
| Account | field search | `account_id` |
| Customer | field search | `partner_id` with `[('customer_rank', '>', 0)]` |
| Provider | field search | `partner_id` with `[('supplier_rank', '>', 0)]` |
| Invoice | field search | `move_id` |

### Action & Menu

- `ir.actions.act_window` opening list view by default, with pivot as secondary view
- Menu entry under **Accounting → Reporting → Account Ledger**

## PDF Report

QWeb template (`report.account_ledger_report_document`) rendering the records passed to it in a table with the same columns as the list view (Date, Account, Reference, Partner, Debit, Credit) plus a totals row (sum of debit and credit).

`ir.actions.report` linked to the list view via a **Print** button.

## Excel Export

Uses Odoo's native list view export button — no additional code needed.

## Security

`ir.model.access.csv` grants read access to `account.ledger.report` for:
- `account.group_account_readonly` (Accounting read-only users)
- `account.group_account_user` (Accountants)
- `account.group_account_manager` (Accounting managers)
- `base.group_system` (Technical administrators)

## File Structure

```
custom-addons/account_ledger_report/
├── __init__.py
├── __manifest__.py
├── models/
│   ├── __init__.py
│   └── account_ledger_report.py
├── views/
│   └── account_ledger_report_views.xml
├── report/
│   └── account_ledger_report_template.xml
└── security/
    └── ir.model.access.csv
```

## Out of Scope

- Draft or cancelled journal entries (only posted)
- Running/cumulative balance column
- Custom date range presets (use standard search filters)
- Analytic accounting fields
