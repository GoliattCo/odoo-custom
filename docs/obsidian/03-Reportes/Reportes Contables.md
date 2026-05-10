# Reportes Contables

#reporte

[[🗺️ Mapa del Proyecto]] > [[co_accounting_extended]]

---

## Los 7 Reportes Personalizados

Todos los reportes comparten el mismo patrón de filtros/agrupaciones:

> **Filtros comunes:** Empresa · Centro de Costo · Unidad de Negocio · Código de Ítem · Auxiliar Abierto

| Módulo | Reporte | Versión |
|--------|---------|---------|
| [[account_ledger_report]] | Mayor de Cuentas | 19.0.1.0.0 |
| [[account_general_ledger]] | Libro Mayor | 19.0.1.0.0 |
| [[account_balance_sheet]] | Balance General | 19.0.1.0.0 |
| [[account_profit_loss]] | Estado de Resultados | 19.0.1.0.0 |
| [[account_aged_receivable]] | Cartera por Cobrar | 19.0.1.0.0 |
| [[account_aged_payable]] | Cartera por Pagar | 19.0.1.0.0 |
| [[account_cash_flow]] | Flujo de Efectivo | 19.0.1.0.0 |

---

## Dependencias comunes

Todos dependen de: `account` + `co_accounting_extended`

---

## Módulo adicional

- [[account_product_category_accounts]] — Cuentas por categoría de producto (depende solo de `account`, `product`)
