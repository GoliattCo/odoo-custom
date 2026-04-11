# Finance Dashboard — Design Spec

**Date:** 2026-04-10
**Module:** `co_dashboards` (new)
**Odoo Version:** 19.0

---

## 1. Overview

Create a new `co_dashboards` module providing a Finance Dashboard using Odoo's `board.board` portlet pattern. The dashboard embeds 9 KPI sections as graph, pivot, and list views, covering P&L, cash flow, aged receivables/payables, budget vs actual, balance sheet, bank balances, fixed assets, and top partner balances. Defaults to current year with user-selectable date filters per portlet.

---

## 2. Module Structure

```
co_dashboards/
├── __init__.py
├── __manifest__.py
├── models/
│   ├── __init__.py
│   └── co_dashboard_bank_balance.py
├── views/
│   ├── finance_dashboard_views.xml
│   ├── finance_board_view.xml
│   └── co_menus.xml
├── security/
│   └── ir.model.access.csv
└── i18n/
    └── es_419.po
```

**Dependencies:** `board`, `account`, `co_accounting_extended`, `co_budget`, `co_fixed_assets`

---

## 3. New Model

### `co.dashboard.bank.balance` (SQL View)

Aggregates `account.move.line` balances per bank/cash journal.

**Fields:**

| Field | Type | Description |
|---|---|---|
| journal_id | Many2one(account.journal) | Bank/cash journal |
| journal_name | Char | Journal display name |
| balance | Float | Net balance (debit - credit) |
| company_id | Many2one(res.company) | Company |

**SQL:**
```sql
SELECT
    row_number() OVER () AS id,
    aml.journal_id,
    aj.name AS journal_name,
    SUM(aml.debit - aml.credit) AS balance,
    aml.company_id
FROM account_move_line aml
JOIN account_journal aj ON aj.id = aml.journal_id
JOIN account_move am ON am.id = aml.move_id
WHERE aj.type IN ('bank', 'cash')
  AND am.state = 'posted'
GROUP BY aml.journal_id, aj.name, aml.company_id
```

---

## 4. KPI Sections

### 4.1 P&L Summary
- **Model:** `account.profit.loss`
- **View:** Graph (bar)
- **Measures:** Debit, Credit
- **Group By:** Account Class
- **Search:** Date filters (This Month / This Quarter / This Year / Custom)
- **Default:** `search_default_this_year: 1`

### 4.2 Cash Flow
- **Model:** `account.cash.flow`
- **View:** Graph (line)
- **Measures:** Cash In, Cash Out, Net Flow
- **Group By:** Date (month)
- **Search:** Date filters
- **Default:** `search_default_this_year: 1`

### 4.3 Aged Receivables
- **Model:** `account.aged.receivable`
- **View:** Graph (bar)
- **Measures:** Amount Residual
- **Group By:** Aging Bucket
- **Search:** Partner filter, date filter

### 4.4 Aged Payables
- **Model:** `account.aged.payable`
- **View:** Graph (bar)
- **Measures:** Amount Residual
- **Group By:** Aging Bucket
- **Search:** Partner filter, date filter

### 4.5 Budget vs Actual
- **Model:** `co.budget.line`
- **View:** Graph (bar)
- **Measures:** Planned Amount, Actual Amount
- **Group By:** Budget Position
- **Search:** Budget filter, period filter
- **Default:** Current active budget

### 4.6 Balance Sheet Summary
- **Model:** `account.balance.sheet`
- **View:** Graph (bar)
- **Measures:** Debit, Credit
- **Group By:** Account Class
- **Search:** Date filter
- **Default:** `search_default_this_year: 1`

### 4.7 Bank/Cash Balances
- **Model:** `co.dashboard.bank.balance`
- **View:** Graph (pie)
- **Measures:** Balance
- **Group By:** Journal Name
- **Search:** Company filter (multi-company)

### 4.8 Fixed Assets
- **Model:** `co.fixed.asset`
- **View:** Graph (bar)
- **Measures:** Gross Value, Accumulated Depreciation, Net Book Value
- **Group By:** Asset Category
- **Search:** State filter, date filter

### 4.9 Top Receivable/Payable Partners
- **Model:** `account.move.line`
- **View:** Pivot
- **Measures:** Amount Residual
- **Group By:** Partner (rows), Account Type receivable/payable (columns)
- **Search:** Filter posted entries only, non-zero residual
- **Default:** Top partners by residual amount

---

## 5. Board Layout

The board uses style `2-1` (wider left, narrower right).

```xml
<board style="2-1">
  <column>
    <!-- Left: P&L, Budget vs Actual, Aged Receivables, Aged Payables -->
    <action name="action_dashboard_pnl" string="Estado de Resultados"/>
    <action name="action_dashboard_budget" string="Presupuesto vs Real"/>
    <action name="action_dashboard_aged_receivable" string="Cartera por Cobrar"/>
    <action name="action_dashboard_aged_payable" string="Cartera por Pagar"/>
  </column>
  <column>
    <!-- Right: Cash Flow, Bank Balances, Balance Sheet, Fixed Assets, Top Partners -->
    <action name="action_dashboard_cashflow" string="Flujo de Caja"/>
    <action name="action_dashboard_bank_balance" string="Saldos Bancarios"/>
    <action name="action_dashboard_balance_sheet" string="Balance General"/>
    <action name="action_dashboard_fixed_assets" string="Activos Fijos"/>
    <action name="action_dashboard_top_partners" string="Principales Terceros"/>
  </column>
</board>
```

---

## 6. Menu Structure

Under Accounting (`account.menu_finance`):

- "Tablero Financiero" (sequence 0) → opens the board action

---

## 7. Security

- `co.dashboard.bank.balance`: read access for `account.group_account_user`, full CRUD for `account.group_account_manager`
- Board view: accessible to all internal users (standard `board.board` access)

---

## 8. Translations

All strings in Spanish (es_CO/es_419):
- Menu: "Tablero Financiero"
- Board title: "Tablero Financiero"
- All portlet titles in Spanish (as shown in section 5)
- Field labels on `co.dashboard.bank.balance` translated
- Search filter labels translated

---

## 9. Out of Scope

- Payroll dashboard (separate implementation)
- Purchase/Warehouse dashboard (separate implementation)
- Club Management dashboard (separate implementation)
- Drill-down from dashboard portlets to detail records (Odoo handles this natively via portlet click)
- Export/PDF of dashboard (not supported by board.board)
