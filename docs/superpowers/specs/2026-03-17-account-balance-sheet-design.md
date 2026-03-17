---
title: account_balance_sheet — Design Spec
date: 2026-03-17
status: approved
---

# account_balance_sheet

## Goal

A new standalone Odoo 18 Community module that provides a Balance Sheet report showing cumulative account balances as of a selected date. Supports on-screen analysis (list + pivot views) and a hierarchical PDF export grouped by PUC class (1=Activo, 2=Pasivo, 3=Patrimonio).

## Module

**Name:** `account_balance_sheet`
**Depends:** `['account']`

## Data Model

**Model:** `account.balance.sheet`
- `_auto = False` — backed by a SQL view, not a real table
- `_description = 'Balance Sheet'`
- `_order = 'account_code asc, id asc'`
- `_rec_name = 'move_name'`
- Read-only (no create/write/unlink)

Only **posted** journal entries are included (`parent_state = 'posted'`). Only PUC classes 1, 2, 3 (Balance Sheet accounts).

**Cumulative balance:** The SQL view returns one row per posted journal entry line — it does not aggregate. Cumulative balance as of a date is achieved when the user applies a `date <= X` filter; the list view aggregates via `sum` aggregators.

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `date` | `fields.Date` | Entry date from `account_move.date` (Date, not Datetime — required for `date <=` filter semantics) |
| `account_id` | Many2one(account.account) | Ledger account |
| `account_code` | Char | Account code from `code_store` JSON field |
| `account_name` | Char, `translate=True` | Account name from `aa.name` — translatable Char avoids multi-company access error on export |
| `account_class` | Char | First digit of account code: `'1'`, `'2'`, or `'3'` |
| `move_id` | Many2one(account.move) | Journal entry |
| `move_name` | Char | Journal entry sequence number (e.g. `INV/2024/001`) from `account_move.name` |
| `partner_id` | Many2one(res.partner) | Partner |
| `debit` | Monetary, `currency_field='currency_id'` | Debit amount (company currency) |
| `credit` | Monetary, `currency_field='currency_id'` | Credit amount (company currency) |
| `balance` | Monetary, `currency_field='currency_id'` | `debit - credit` (SQL, always debit minus credit — sign flip only applied in PDF display) |
| `company_id` | Many2one(res.company) | Company |
| `currency_id` | Many2one(res.currency) | Company currency — required as `currency_field` for all Monetary fields |

### SQL

Follows the **same `code_store` pattern as `account_ledger_report`** (confirmed working in this codebase). `rco.parent_path` is a field on `res_company` used as the JSON key for `code_store`.

`currency_id` uses `rc.id` (from a joined `res_currency` table), **not** `rco.currency_id` — same as `account_ledger_report`.

If `code_store` returns NULL for a row (e.g. wrong company key), `LEFT(NULL, 1)` = NULL which does not match `IN ('1','2','3')` — those rows are silently excluded, which is correct behavior.

```sql
SELECT
    aml.id                                                                          AS id,
    am.date                                                                         AS date,
    aml.account_id                                                                  AS account_id,
    aa.code_store->>(SPLIT_PART(rco.parent_path, '/', 1)::text)                    AS account_code,
    aa.name                                                                         AS account_name,
    LEFT(aa.code_store->>(SPLIT_PART(rco.parent_path, '/', 1)::text), 1)           AS account_class,
    aml.move_id                                                                     AS move_id,
    am.name                                                                         AS move_name,
    aml.partner_id                                                                  AS partner_id,
    aml.debit                                                                       AS debit,
    aml.credit                                                                      AS credit,
    aml.debit - aml.credit                                                          AS balance,
    aml.company_id                                                                  AS company_id,
    rc.id                                                                           AS currency_id
FROM account_move_line aml
JOIN account_move    am  ON am.id  = aml.move_id
JOIN account_account aa  ON aa.id  = aml.account_id
JOIN res_company     rco ON rco.id = aml.company_id
JOIN res_currency    rc  ON rc.id  = rco.currency_id
WHERE aml.parent_state = 'posted'
  AND LEFT(aa.code_store->>(SPLIT_PART(rco.parent_path, '/', 1)::text), 1) IN ('1', '2', '3')
```

Multi-company: Odoo's standard `ir.rule` record rules handle per-company filtering automatically.

## Views

### List View

Columns: Account Class · Account Code · Account · Reference · Partner · Debit · Credit · Balance

- "Reference" column maps to `move_name`
- `sum` aggregators on Debit, Credit, and Balance
- Default grouping: `account_class` then `account_id` (activated via `search_default_group_by_account_class: 1` and `search_default_group_by_account: 1` in action context)
- **Print PDF** button in list header calls a Python method returning the report action with `active_domain`
- **Sign convention:** `balance` shown as raw `debit - credit` in the list view. Sign flip is **PDF-only**.

### Pivot View

Default configuration:
- Rows: `account_class` → `account_id`
- Measures: Debit, Credit, Balance (all raw `debit - credit`)

### Search View

Two separate mechanisms for the date:

1. **`<field>` with `filter_domain`** — manual date picker, lets user type any "as of date":
   ```xml
   <field name="date" string="Al Corte De" filter_domain="[('date', '&lt;=', self)]"/>
   ```
   This is the interactive picker. It does NOT conflict with the named filter below.

2. **Named filter `date_to`** — static today cutoff, auto-activated on open:
   ```xml
   <filter name="date_to"
           string="Al Corte De (Hoy)"
           domain="[('date', '&lt;=', context_today().strftime('%Y-%m-%d'))]"/>
   ```
   Auto-activated via `search_default_date_to: 1` in action context.

Full search view elements:

| Element | Type | Purpose |
|---|---|---|
| `date` with `filter_domain` | `<field>` | Manual "as of date" picker |
| `date_to` | `<filter>` | Default today cutoff (auto-activated) |
| `group_by_account_class` | `<filter context="{'group_by':'account_class'}">` | Group by Clase |
| `group_by_account` | `<filter context="{'group_by':'account_id'}">` | Group by Cuenta |
| Activo | `<filter domain="[('account_class','=','1')]">` | Class 1 only |
| Pasivo | `<filter domain="[('account_class','=','2')]">` | Class 2 only |
| Patrimonio | `<filter domain="[('account_class','=','3')]">` | Class 3 only |
| `account_id` | `<field>` | Search by account |
| `partner_id` | `<field>` | Search by partner |
| `move_id` | `<field>` | Search by journal entry |

### Action & Menu

```python
context={
    'search_default_date_to': 1,
    'search_default_group_by_account_class': 1,
    'search_default_group_by_account': 1,
}
```

Menu: **Accounting → Reporting → Balance General**

## PDF Report

QWeb template `report.account_balance_sheet_document`.

### Structure

```
Balance General — Al [fecha]
─────────────────────────────────────────────────────
1. ACTIVO
   [Código]  [Cuenta]                     [Saldo]
   ...
   TOTAL ACTIVO                           [suma]

2. PASIVO
   [Código]  [Cuenta]                     [Saldo]
   ...
   TOTAL PASIVO                           [suma]

3. PATRIMONIO
   [Código]  [Cuenta]                     [Saldo]
   ...
   TOTAL PATRIMONIO                       [suma]

─────────────────────────────────────────────────────
TOTAL PASIVO + PATRIMONIO                 [suma]
ACTIVO = PASIVO + PATRIMONIO              ✓ / ✗
```

### Balance Sign Convention (PDF only)

The SQL `balance` field is always `debit - credit`. The PDF controller applies sign flip before rendering:

- **Activo (class 1):** displayed saldo = `balance` (debit − credit)
- **Pasivo (class 2):** displayed saldo = `abs(balance)` if credit-normal, i.e. `−balance` when credit > debit
- **Patrimonio (class 3):** displayed saldo = `−balance` (credit − debit)

Simpler implementation: `displayed_saldo = balance if account_class == '1' else -balance`.

### Accounting Equation Check

```python
equation_diff = total_activo_displayed - (total_pasivo_displayed + total_patrimonio_displayed)
equation_ok = abs(equation_diff) < 0.01
```

QWeb shows ✓ if `equation_ok`, otherwise ✗ with `equation_diff` formatted as currency amount.

### Python Report Model (`AbstractModel`)

Model name: `report.account_balance_sheet.document`

`_get_report_values(self, docids, data=None)`:

1. Reads `domain` from `data` (a Python list passed directly by the Print button's server method — no `eval()` needed since it's passed as a Python object, not a string)
2. Falls back to `[('id', 'in', docids)]` if no domain in data
3. Searches `self.env['account.balance.sheet'].search(domain)`
4. Groups rows: `{account_class: {account_id: {'account_code': ..., 'account_name': ..., 'debit': sum, 'credit': sum}}}`
5. Computes `displayed_saldo` per account (sign flip for classes 2, 3)
6. Computes `total_activo`, `total_pasivo`, `total_patrimonio`, `total_pasivo_patrimonio`
7. Computes `equation_diff` and `equation_ok`
8. Returns `{'sections': [...], 'totals': {...}, 'equation_ok': bool, 'equation_diff': float}`

**Print button wiring:** The list view header button calls a Python method `action_print_balance_sheet` on the model:

```python
def action_print_balance_sheet(self):
    domain = self._context.get('active_domain', [])
    return self.env.ref('account_balance_sheet.action_report_balance_sheet').report_action(
        self, data={'domain': domain}
    )
```

`ir.actions.report` of type `qweb-pdf`, model `account.balance.sheet`.

## Excel Export

Uses Odoo's native list view export button — no additional code needed.

## Security

`ir.model.access.csv` grants read access to `account.balance.sheet` for:
- `account.group_account_readonly`
- `account.group_account_user`
- `account.group_account_manager`
- `base.group_system`

## i18n

`.po` files for `es` and `es_419` covering:
- Menu: *Balance General*
- Section headers: *Activo, Pasivo, Patrimonio*
- Totals: *Total Activo, Total Pasivo, Total Patrimonio, Total Pasivo + Patrimonio*
- PDF header: *Balance General — Al [fecha]*
- Search labels: *Al Corte De, Clase, Cuenta, Activo, Pasivo, Patrimonio*
- Column headers: *Clase, Código, Cuenta, Referencia, Socio, Debe, Haber, Saldo*

## Tests

`tests/test_balance_sheet.py` (`TransactionCase`):

**Setup:**
- Activate Spanish: `self.env['res.lang']._activate_lang('es_CO')`
- Create accounts using `self.env['account.account'].create({'code': '10', 'name': 'Caja', ...})` — setting `code` populates `code_store` via the Odoo 18 ORM automatically
- Create accounts for codes `10` (Activo), `21` (Pasivo), `31` (Patrimonio)
- Post a balanced journal entry: debit `10` = 1000, credit `21` = 500, credit `31` = 500

**Assertions:**
1. View returns 3 rows with domain `[]`
2. Row `account_code='10'`: `account_class='1'`, `debit=1000`, `credit=0`, `balance=1000`
3. Row `account_code='21'`: `account_class='2'`, `debit=0`, `credit=500`, `balance=-500`
4. Row `account_code='31'`: `account_class='3'`, `debit=0`, `credit=500`, `balance=-500`
5. Accounting equation: `sum(balance where class='1') + sum(balance where class in ('2','3')) == 0`
6. Date cutoff: an entry dated tomorrow is excluded when domain `[('date', '<=', fields.Date.today())]` applied
7. Spanish field label: `self.env['account.balance.sheet'].with_context(lang='es_CO')._fields['account_class'].string == 'Clase'`

## File Structure

```
custom-addons/account_balance_sheet/
├── __init__.py
├── __manifest__.py
├── models/
│   ├── __init__.py
│   └── account_balance_sheet.py
├── views/
│   └── account_balance_sheet_views.xml
├── report/
│   ├── __init__.py
│   ├── account_balance_sheet_report.py    (AbstractModel _get_report_values)
│   └── account_balance_sheet_template.xml (QWeb template)
├── security/
│   └── ir.model.access.csv
├── tests/
│   ├── __init__.py
│   └── test_balance_sheet.py
└── i18n/
    ├── es.po
    └── es_419.po
```

## Out of Scope

- Draft or cancelled journal entries (only posted)
- Income Statement accounts (PUC classes 4, 5, 6)
- Custom fiscal year presets
- Analytic accounting fields
- Comparative columns (previous period)
- Running balance per account
