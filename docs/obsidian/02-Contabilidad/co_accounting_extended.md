# co_accounting_extended

#contabilidad

[[🗺️ Mapa del Proyecto]] > [[Reportes Contables]]

**Versión:** 19.0.2.0.0  
**Nombre:** Contabilidad Colombiana Extendida  
**Depends:** `account`, `analytic`, `mail`

---

## Propósito

Módulo principal de extensión contable para Colombia. Agrega dimensiones analíticas propias (centros de costo, códigos de ítem, unidades de negocio) y conceptos contables al plan de cuentas Odoo.

---

## Modelos Propios

| Modelo | Descripción | Jerarquía |
|--------|-------------|-----------|
| `co.cost.center` | Centros de Costo | Grupo / Detalle |
| `co.item.code` | Códigos de Ítem | Grupo / Detalle |
| `co.business.unit` | Unidades de Negocio | — |
| `co.accounting.concept` | Conceptos Contables | code + name + account |
| `co.auto.posting.rule` | Reglas de Contabilización Automática | — |
| `co.formulated.concept` | Conceptos Formulados (fórmulas) | — |

---

## Extensiones a Modelos Odoo

### `account.account`
- `requires_cost_center` — obliga llenar centro de costo
- `requires_item_code` — obliga llenar código de ítem
- `requires_auxiliar_abierto` — obliga llenar auxiliar abierto

### `account.move.line`
- `cost_center_id` → `co.cost.center`
- `item_code_id` → `co.item.code`
- `auxiliar_abierto` — campo de auxiliar
- `business_unit_id` → `co.business.unit`
- `concepto_contable_id` → `co.accounting.concept` (con onchange auto-fill)

### `account.move`
- `debit_credit_difference` — diferencia débito/crédito
- Validación en post
- Reporte PDF del asiento

---

## Wizards

| Wizard | Función |
|--------|---------|
| Cierre de Año | Genera asientos de cierre fiscal |
| Exportar CSV | Exporta movimientos a CSV |
| Importar CSV | Importa movimientos desde CSV |
| Exportar Excel | Exporta a formato Excel |

---

## Módulos que dependen de este

- [[account_ledger_report]]
- [[account_general_ledger]]
- [[account_balance_sheet]]
- [[account_profit_loss]]
- [[account_aged_receivable]]
- [[account_aged_payable]]
- [[account_cash_flow]]
- [[goliatt_contabilidad]]
- [[co_dashboards]]
