# Finance Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a `co_dashboards` module with a Finance Dashboard using Odoo's `board.board` portlet pattern, embedding 9 KPI graph/pivot views for P&L, cash flow, aged receivables/payables, budget vs actual, balance sheet, bank balances, fixed assets, and top partners.

**Architecture:** New module `co_dashboards` creates graph views and window actions for each KPI, then assembles them into a `board.board` form view. One new SQL-view model (`co.dashboard.bank.balance`) aggregates bank/cash journal balances. All other KPIs reuse existing report models.

**Tech Stack:** Odoo 19.0, Python 3.12, PostgreSQL 15, XML views, board.board portlet system

---

## File Map

### New Files (all under `custom-addons/co_dashboards/`)

| File | Responsibility |
|---|---|
| `__init__.py` | Module init |
| `__manifest__.py` | Module manifest with dependencies |
| `models/__init__.py` | Model imports |
| `models/co_dashboard_bank_balance.py` | SQL view model for bank/cash balances |
| `views/finance_dashboard_views.xml` | 9 graph/pivot views + search views + window actions |
| `views/finance_board_view.xml` | The board form view with portlets |
| `views/co_menus.xml` | Menu under Accounting |
| `security/ir.model.access.csv` | Access rules for bank balance model |
| `i18n/es_419.po` | Spanish translations |

---

## Task 1: Module Scaffold & Bank Balance Model

**Files:**
- Create: `custom-addons/co_dashboards/__init__.py`
- Create: `custom-addons/co_dashboards/__manifest__.py`
- Create: `custom-addons/co_dashboards/models/__init__.py`
- Create: `custom-addons/co_dashboards/models/co_dashboard_bank_balance.py`
- Create: `custom-addons/co_dashboards/security/ir.model.access.csv`

- [ ] **Step 1: Create `__init__.py`**

```python
from . import models
```

- [ ] **Step 2: Create `__manifest__.py`**

```python
{
    'name': 'Tableros de Gestión',
    'version': '19.0.1.0.0',
    'summary': 'Tableros financieros con KPIs para contabilidad, presupuesto y activos',
    'category': 'Accounting/Accounting',
    'author': 'Manuel Caro',
    'license': 'LGPL-3',
    'depends': [
        'board',
        'account',
        'co_accounting_extended',
        'account_profit_loss',
        'account_cash_flow',
        'account_aged_receivable',
        'account_aged_payable',
        'account_balance_sheet',
        'co_budget',
        'co_fixed_assets',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/finance_dashboard_views.xml',
        'views/finance_board_view.xml',
        'views/co_menus.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': False,
}
```

- [ ] **Step 3: Create `models/__init__.py`**

```python
from . import co_dashboard_bank_balance
```

- [ ] **Step 4: Create `models/co_dashboard_bank_balance.py`**

```python
from odoo import fields, models, tools


class CoDashboardBankBalance(models.Model):
    _name = 'co.dashboard.bank.balance'
    _description = 'Bank/Cash Balance'
    _auto = False
    _order = 'balance desc'

    journal_id = fields.Many2one('account.journal', string='Diario', readonly=True)
    journal_name = fields.Char(string='Diario', readonly=True)
    balance = fields.Monetary(string='Saldo', readonly=True)
    company_id = fields.Many2one('res.company', string='Empresa', readonly=True)
    currency_id = fields.Many2one('res.currency', string='Moneda', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    row_number() OVER () AS id,
                    aml.journal_id,
                    aj.name AS journal_name,
                    SUM(aml.debit - aml.credit) AS balance,
                    aml.company_id,
                    aj.currency_id AS currency_id
                FROM account_move_line aml
                JOIN account_journal aj ON aj.id = aml.journal_id
                JOIN account_move am ON am.id = aml.move_id
                WHERE aj.type IN ('bank', 'cash')
                  AND am.state = 'posted'
                GROUP BY aml.journal_id, aj.name, aml.company_id, aj.currency_id
            )
        """ % self._table)
```

- [ ] **Step 5: Create `security/ir.model.access.csv`**

```csv
id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink
access_co_dashboard_bank_balance_user,co.dashboard.bank.balance user,model_co_dashboard_bank_balance,account.group_account_user,1,0,0,0
access_co_dashboard_bank_balance_manager,co.dashboard.bank.balance manager,model_co_dashboard_bank_balance,account.group_account_manager,1,1,1,1
```

- [ ] **Step 6: Commit**

```bash
git add custom-addons/co_dashboards/
git commit -m "feat: scaffold co_dashboards module with bank balance SQL view"
```

---

## Task 2: KPI Graph & Pivot Views (All 9)

**Files:**
- Create: `custom-addons/co_dashboards/views/finance_dashboard_views.xml`

- [ ] **Step 1: Create `views/finance_dashboard_views.xml`**

This file contains all 9 KPI views: a search view (for date filtering), a graph/pivot view, and a window action for each.

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>

    <!-- ============================================================ -->
    <!-- 1. P&L SUMMARY                                                -->
    <!-- ============================================================ -->
    <record id="dashboard_pnl_search" model="ir.ui.view">
        <field name="name">dashboard.pnl.search</field>
        <field name="model">account.profit.loss</field>
        <field name="arch" type="xml">
            <search string="Estado de Resultados">
                <field name="account_class"/>
                <field name="account_id"/>
                <separator/>
                <filter name="this_month" string="Este Mes"
                        domain="[('date', '&gt;=', (context_today() - relativedelta(day=1)).strftime('%Y-%m-%d')),
                                 ('date', '&lt;=', context_today().strftime('%Y-%m-%d'))]"/>
                <filter name="this_quarter" string="Este Trimestre"
                        domain="[('date', '&gt;=', (context_today() - relativedelta(month=((context_today().month - 1) // 3) * 3 + 1, day=1)).strftime('%Y-%m-%d')),
                                 ('date', '&lt;=', context_today().strftime('%Y-%m-%d'))]"/>
                <filter name="this_year" string="Este Año"
                        domain="[('date', '&gt;=', (context_today() - relativedelta(month=1, day=1)).strftime('%Y-%m-%d')),
                                 ('date', '&lt;=', context_today().strftime('%Y-%m-%d'))]"/>
            </search>
        </field>
    </record>

    <record id="dashboard_pnl_graph" model="ir.ui.view">
        <field name="name">dashboard.pnl.graph</field>
        <field name="model">account.profit.loss</field>
        <field name="arch" type="xml">
            <graph string="Estado de Resultados" type="bar">
                <field name="account_class" type="row"/>
                <field name="balance" type="measure"/>
            </graph>
        </field>
    </record>

    <record id="action_dashboard_pnl" model="ir.actions.act_window">
        <field name="name">Estado de Resultados</field>
        <field name="res_model">account.profit.loss</field>
        <field name="view_mode">graph</field>
        <field name="view_id" ref="dashboard_pnl_graph"/>
        <field name="search_view_id" ref="dashboard_pnl_search"/>
        <field name="context">{'search_default_this_year': 1}</field>
    </record>

    <!-- ============================================================ -->
    <!-- 2. CASH FLOW                                                  -->
    <!-- ============================================================ -->
    <record id="dashboard_cashflow_search" model="ir.ui.view">
        <field name="name">dashboard.cashflow.search</field>
        <field name="model">account.cash.flow</field>
        <field name="arch" type="xml">
            <search string="Flujo de Caja">
                <field name="journal_id"/>
                <separator/>
                <filter name="this_month" string="Este Mes"
                        domain="[('date', '&gt;=', (context_today() - relativedelta(day=1)).strftime('%Y-%m-%d')),
                                 ('date', '&lt;=', context_today().strftime('%Y-%m-%d'))]"/>
                <filter name="this_quarter" string="Este Trimestre"
                        domain="[('date', '&gt;=', (context_today() - relativedelta(month=((context_today().month - 1) // 3) * 3 + 1, day=1)).strftime('%Y-%m-%d')),
                                 ('date', '&lt;=', context_today().strftime('%Y-%m-%d'))]"/>
                <filter name="this_year" string="Este Año"
                        domain="[('date', '&gt;=', (context_today() - relativedelta(month=1, day=1)).strftime('%Y-%m-%d')),
                                 ('date', '&lt;=', context_today().strftime('%Y-%m-%d'))]"/>
            </search>
        </field>
    </record>

    <record id="dashboard_cashflow_graph" model="ir.ui.view">
        <field name="name">dashboard.cashflow.graph</field>
        <field name="model">account.cash.flow</field>
        <field name="arch" type="xml">
            <graph string="Flujo de Caja" type="line">
                <field name="date" interval="month" type="row"/>
                <field name="cash_in" type="measure"/>
                <field name="cash_out" type="measure"/>
                <field name="net_flow" type="measure"/>
            </graph>
        </field>
    </record>

    <record id="action_dashboard_cashflow" model="ir.actions.act_window">
        <field name="name">Flujo de Caja</field>
        <field name="res_model">account.cash.flow</field>
        <field name="view_mode">graph</field>
        <field name="view_id" ref="dashboard_cashflow_graph"/>
        <field name="search_view_id" ref="dashboard_cashflow_search"/>
        <field name="context">{'search_default_this_year': 1}</field>
    </record>

    <!-- ============================================================ -->
    <!-- 3. AGED RECEIVABLES                                           -->
    <!-- ============================================================ -->
    <record id="dashboard_aged_receivable_graph" model="ir.ui.view">
        <field name="name">dashboard.aged.receivable.graph</field>
        <field name="model">account.aged.receivable</field>
        <field name="arch" type="xml">
            <graph string="Cartera por Cobrar" type="bar">
                <field name="aging_bucket" type="row"/>
                <field name="amount_residual" type="measure"/>
            </graph>
        </field>
    </record>

    <record id="action_dashboard_aged_receivable" model="ir.actions.act_window">
        <field name="name">Cartera por Cobrar</field>
        <field name="res_model">account.aged.receivable</field>
        <field name="view_mode">graph</field>
        <field name="view_id" ref="dashboard_aged_receivable_graph"/>
    </record>

    <!-- ============================================================ -->
    <!-- 4. AGED PAYABLES                                              -->
    <!-- ============================================================ -->
    <record id="dashboard_aged_payable_graph" model="ir.ui.view">
        <field name="name">dashboard.aged.payable.graph</field>
        <field name="model">account.aged.payable</field>
        <field name="arch" type="xml">
            <graph string="Cartera por Pagar" type="bar">
                <field name="aging_bucket" type="row"/>
                <field name="amount_residual" type="measure"/>
            </graph>
        </field>
    </record>

    <record id="action_dashboard_aged_payable" model="ir.actions.act_window">
        <field name="name">Cartera por Pagar</field>
        <field name="res_model">account.aged.payable</field>
        <field name="view_mode">graph</field>
        <field name="view_id" ref="dashboard_aged_payable_graph"/>
    </record>

    <!-- ============================================================ -->
    <!-- 5. BUDGET VS ACTUAL                                           -->
    <!-- ============================================================ -->
    <record id="dashboard_budget_search" model="ir.ui.view">
        <field name="name">dashboard.budget.search</field>
        <field name="model">co.budget.line</field>
        <field name="arch" type="xml">
            <search string="Presupuesto vs Real">
                <field name="budget_id"/>
                <field name="budget_position_id"/>
                <field name="account_id"/>
                <separator/>
                <filter name="active_budget" string="Presupuesto Activo"
                        domain="[('budget_state', '=', 'confirmed')]"/>
            </search>
        </field>
    </record>

    <record id="dashboard_budget_graph" model="ir.ui.view">
        <field name="name">dashboard.budget.graph</field>
        <field name="model">co.budget.line</field>
        <field name="arch" type="xml">
            <graph string="Presupuesto vs Real" type="bar">
                <field name="budget_position_id" type="row"/>
                <field name="planned_amount" type="measure"/>
                <field name="actual_amount" type="measure"/>
            </graph>
        </field>
    </record>

    <record id="action_dashboard_budget" model="ir.actions.act_window">
        <field name="name">Presupuesto vs Real</field>
        <field name="res_model">co.budget.line</field>
        <field name="view_mode">graph</field>
        <field name="view_id" ref="dashboard_budget_graph"/>
        <field name="search_view_id" ref="dashboard_budget_search"/>
        <field name="context">{'search_default_active_budget': 1}</field>
    </record>

    <!-- ============================================================ -->
    <!-- 6. BALANCE SHEET SUMMARY                                      -->
    <!-- ============================================================ -->
    <record id="dashboard_balance_sheet_search" model="ir.ui.view">
        <field name="name">dashboard.balance.sheet.search</field>
        <field name="model">account.balance.sheet</field>
        <field name="arch" type="xml">
            <search string="Balance General">
                <field name="account_class"/>
                <separator/>
                <filter name="this_month" string="Este Mes"
                        domain="[('date', '&gt;=', (context_today() - relativedelta(day=1)).strftime('%Y-%m-%d')),
                                 ('date', '&lt;=', context_today().strftime('%Y-%m-%d'))]"/>
                <filter name="this_quarter" string="Este Trimestre"
                        domain="[('date', '&gt;=', (context_today() - relativedelta(month=((context_today().month - 1) // 3) * 3 + 1, day=1)).strftime('%Y-%m-%d')),
                                 ('date', '&lt;=', context_today().strftime('%Y-%m-%d'))]"/>
                <filter name="this_year" string="Este Año"
                        domain="[('date', '&gt;=', (context_today() - relativedelta(month=1, day=1)).strftime('%Y-%m-%d')),
                                 ('date', '&lt;=', context_today().strftime('%Y-%m-%d'))]"/>
            </search>
        </field>
    </record>

    <record id="dashboard_balance_sheet_graph" model="ir.ui.view">
        <field name="name">dashboard.balance.sheet.graph</field>
        <field name="model">account.balance.sheet</field>
        <field name="arch" type="xml">
            <graph string="Balance General" type="bar">
                <field name="account_class" type="row"/>
                <field name="balance" type="measure"/>
            </graph>
        </field>
    </record>

    <record id="action_dashboard_balance_sheet" model="ir.actions.act_window">
        <field name="name">Balance General</field>
        <field name="res_model">account.balance.sheet</field>
        <field name="view_mode">graph</field>
        <field name="view_id" ref="dashboard_balance_sheet_graph"/>
        <field name="search_view_id" ref="dashboard_balance_sheet_search"/>
        <field name="context">{'search_default_this_year': 1}</field>
    </record>

    <!-- ============================================================ -->
    <!-- 7. BANK/CASH BALANCES                                         -->
    <!-- ============================================================ -->
    <record id="dashboard_bank_balance_graph" model="ir.ui.view">
        <field name="name">dashboard.bank.balance.graph</field>
        <field name="model">co.dashboard.bank.balance</field>
        <field name="arch" type="xml">
            <graph string="Saldos Bancarios" type="pie">
                <field name="journal_name" type="row"/>
                <field name="balance" type="measure"/>
            </graph>
        </field>
    </record>

    <record id="action_dashboard_bank_balance" model="ir.actions.act_window">
        <field name="name">Saldos Bancarios</field>
        <field name="res_model">co.dashboard.bank.balance</field>
        <field name="view_mode">graph</field>
        <field name="view_id" ref="dashboard_bank_balance_graph"/>
    </record>

    <!-- ============================================================ -->
    <!-- 8. FIXED ASSETS                                               -->
    <!-- ============================================================ -->
    <record id="dashboard_fixed_assets_search" model="ir.ui.view">
        <field name="name">dashboard.fixed.assets.search</field>
        <field name="model">co.fixed.asset</field>
        <field name="arch" type="xml">
            <search string="Activos Fijos">
                <field name="category_id"/>
                <field name="state"/>
                <separator/>
                <filter name="running" string="En Uso"
                        domain="[('state', '=', 'running')]"/>
            </search>
        </field>
    </record>

    <record id="dashboard_fixed_assets_graph" model="ir.ui.view">
        <field name="name">dashboard.fixed.assets.graph</field>
        <field name="model">co.fixed.asset</field>
        <field name="arch" type="xml">
            <graph string="Activos Fijos" type="bar">
                <field name="category_id" type="row"/>
                <field name="purchase_value" type="measure"/>
                <field name="accumulated_depreciation" type="measure"/>
                <field name="book_value" type="measure"/>
            </graph>
        </field>
    </record>

    <record id="action_dashboard_fixed_assets" model="ir.actions.act_window">
        <field name="name">Activos Fijos</field>
        <field name="res_model">co.fixed.asset</field>
        <field name="view_mode">graph</field>
        <field name="view_id" ref="dashboard_fixed_assets_graph"/>
        <field name="search_view_id" ref="dashboard_fixed_assets_search"/>
        <field name="context">{'search_default_running': 1}</field>
    </record>

    <!-- ============================================================ -->
    <!-- 9. TOP RECEIVABLE/PAYABLE PARTNERS                            -->
    <!-- ============================================================ -->
    <record id="dashboard_top_partners_search" model="ir.ui.view">
        <field name="name">dashboard.top.partners.search</field>
        <field name="model">account.move.line</field>
        <field name="arch" type="xml">
            <search string="Principales Terceros">
                <field name="partner_id"/>
                <separator/>
                <filter name="posted" string="Publicados"
                        domain="[('parent_state', '=', 'posted')]"/>
                <filter name="receivable_payable" string="Por Cobrar/Pagar"
                        domain="[('account_type', 'in', ('asset_receivable', 'liability_payable'))]"/>
                <filter name="open_items" string="Partidas Abiertas"
                        domain="[('amount_residual', '!=', 0)]"/>
            </search>
        </field>
    </record>

    <record id="dashboard_top_partners_pivot" model="ir.ui.view">
        <field name="name">dashboard.top.partners.pivot</field>
        <field name="model">account.move.line</field>
        <field name="arch" type="xml">
            <pivot string="Principales Terceros">
                <field name="partner_id" type="row"/>
                <field name="account_type" type="col"/>
                <field name="amount_residual" type="measure"/>
            </pivot>
        </field>
    </record>

    <record id="action_dashboard_top_partners" model="ir.actions.act_window">
        <field name="name">Principales Terceros</field>
        <field name="res_model">account.move.line</field>
        <field name="view_mode">pivot</field>
        <field name="view_id" ref="dashboard_top_partners_pivot"/>
        <field name="search_view_id" ref="dashboard_top_partners_search"/>
        <field name="context">{'search_default_posted': 1, 'search_default_receivable_payable': 1, 'search_default_open_items': 1}</field>
    </record>

</odoo>
```

- [ ] **Step 2: Commit**

```bash
git add custom-addons/co_dashboards/views/finance_dashboard_views.xml
git commit -m "feat: add 9 KPI graph/pivot views for finance dashboard"
```

---

## Task 3: Board View & Menu

**Files:**
- Create: `custom-addons/co_dashboards/views/finance_board_view.xml`
- Create: `custom-addons/co_dashboards/views/co_menus.xml`

- [ ] **Step 1: Create `views/finance_board_view.xml`**

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="finance_board_view" model="ir.ui.view">
        <field name="name">Tablero Financiero</field>
        <field name="model">board.board</field>
        <field name="arch" type="xml">
            <form string="Tablero Financiero">
                <board style="2-1">
                    <column>
                        <action name="%(co_dashboards.action_dashboard_pnl)d"
                                string="Estado de Resultados"/>
                        <action name="%(co_dashboards.action_dashboard_budget)d"
                                string="Presupuesto vs Real"/>
                        <action name="%(co_dashboards.action_dashboard_aged_receivable)d"
                                string="Cartera por Cobrar"/>
                        <action name="%(co_dashboards.action_dashboard_aged_payable)d"
                                string="Cartera por Pagar"/>
                    </column>
                    <column>
                        <action name="%(co_dashboards.action_dashboard_cashflow)d"
                                string="Flujo de Caja"/>
                        <action name="%(co_dashboards.action_dashboard_bank_balance)d"
                                string="Saldos Bancarios"/>
                        <action name="%(co_dashboards.action_dashboard_balance_sheet)d"
                                string="Balance General"/>
                        <action name="%(co_dashboards.action_dashboard_fixed_assets)d"
                                string="Activos Fijos"/>
                        <action name="%(co_dashboards.action_dashboard_top_partners)d"
                                string="Principales Terceros"/>
                    </column>
                </board>
            </form>
        </field>
    </record>

    <record id="action_finance_board" model="ir.actions.act_window">
        <field name="name">Tablero Financiero</field>
        <field name="res_model">board.board</field>
        <field name="view_mode">form</field>
        <field name="context">{'disable_toolbar': True}</field>
        <field name="usage">menu</field>
        <field name="view_id" ref="finance_board_view"/>
    </record>
</odoo>
```

- [ ] **Step 2: Create `views/co_menus.xml`**

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <menuitem id="menu_finance_dashboard"
              name="Tablero Financiero"
              parent="account.menu_finance"
              action="action_finance_board"
              sequence="0"/>
</odoo>
```

- [ ] **Step 3: Commit**

```bash
git add custom-addons/co_dashboards/views/finance_board_view.xml \
        custom-addons/co_dashboards/views/co_menus.xml
git commit -m "feat: add finance board view and menu"
```

---

## Task 4: Spanish Translations

**Files:**
- Create: `custom-addons/co_dashboards/i18n/es_419.po`

- [ ] **Step 1: Create `i18n/es_419.po`**

```po
# Translation of Odoo Server.
# This file contains the translation of the following modules:
# 	* co_dashboards
#
msgid ""
msgstr ""
"Project-Id-Version: Odoo Server 19.0\n"
"Report-Msgid-Bugs-To: \n"
"POT-Creation-Date: 2026-04-10 00:00+0000\n"
"PO-Revision-Date: 2026-04-10 00:00+0000\n"
"Last-Translator: \n"
"Language-Team: Spanish (Latin America)\n"
"Language: es_419\n"
"MIME-Version: 1.0\n"
"Content-Type: text/plain; charset=UTF-8\n"
"Content-Transfer-Encoding: 8bit\n"
"Plural-Forms: nplurals=2; plural=(n != 1);\n"

#. module: co_dashboards
#: model:ir.model,name:co_dashboards.model_co_dashboard_bank_balance
msgid "Bank/Cash Balance"
msgstr "Saldo Bancario/Efectivo"

#. module: co_dashboards
#: model:ir.model.fields,field_description:co_dashboards.field_co_dashboard_bank_balance__journal_id
msgid "Journal"
msgstr "Diario"

#. module: co_dashboards
#: model:ir.model.fields,field_description:co_dashboards.field_co_dashboard_bank_balance__journal_name
msgid "Journal Name"
msgstr "Nombre del Diario"

#. module: co_dashboards
#: model:ir.model.fields,field_description:co_dashboards.field_co_dashboard_bank_balance__balance
msgid "Balance"
msgstr "Saldo"
```

- [ ] **Step 2: Commit**

```bash
git add custom-addons/co_dashboards/i18n/es_419.po
git commit -m "feat: add Spanish translations for co_dashboards"
```

---

## Task 5: Install Module & Browser Test

**Files:** None (testing only)

- [ ] **Step 1: Install the module**

```bash
docker compose exec odoo /odoo/odoo-bin -c /etc/odoo/odoo.conf -i co_dashboards --stop-after-init
```

Expected: Module installs without errors. Watch for: missing field references in graph views, XML ID resolution errors for board actions, SQL view creation errors.

- [ ] **Step 2: Restart Odoo**

```bash
docker compose restart odoo
```

- [ ] **Step 3: Browser test**

1. Navigate to Accounting → Tablero Financiero
2. Verify the board loads with 9 portlets
3. Verify each portlet shows a graph or pivot (may show "No data" if no accounting data exists)
4. Verify the P&L, Cash Flow, and Balance Sheet portlets have date filter dropdowns
5. Verify the Budget portlet defaults to active budgets
6. Verify the Fixed Assets portlet defaults to "En Uso" filter
7. Verify the Top Partners portlet shows a pivot with partner rows and receivable/payable columns
8. Verify Bank/Cash Balances shows a pie chart
9. Test dragging portlets to rearrange (standard board feature)

- [ ] **Step 4: Fix any issues and re-test**

Iterate until all 9 portlets render correctly.

- [ ] **Step 5: Final commit if fixes needed**

```bash
git add -u custom-addons/co_dashboards/
git commit -m "fix: resolve dashboard rendering issues"
```
