# 🗺️ Mapa del Proyecto Odoo Goliatt

> Odoo 19 · Docker · PostgreSQL · Colombian Accounting + Club Management

---

## Arquitectura General

```
┌─────────────────────────────────────────────────────┐
│                  ODOO 19 (Docker)                   │
│              http://localhost:8069                  │
├────────────────────┬────────────────────────────────┤
│  Contabilidad CO   │       Club Management          │
│                    │                                │
│  co_accounting_    │  club_core ──► club_golf       │
│  extended          │           ──► club_tennis      │
│  goliatt_conta...  │           ──► club_swimming    │
│                    │           ──► club_sailing     │
│  7 Reportes        │           ──► club_equestrian  │
│  co_budget         │           ──► club_events      │
│  co_bank_rec...    │           ──► club_pos         │
│  co_exogena        │           + 10 más...          │
│  co_payroll        │                                │
│  co_fixed_assets   │  goliatt_pms                   │
└────────────────────┴────────────────────────────────┘
```

---

## Secciones

| Sección | Descripción |
|---------|-------------|
| [[Infraestructura]] | Docker, DB, paths, comandos |
| [[co_accounting_extended]] | Módulo principal de contabilidad |
| [[goliatt_contabilidad]] | App Goliatt - espejo de contabilidad |
| [[Reportes Contables]] | Los 7 reportes personalizados |
| [[Club Core]] | Núcleo de gestión de club |
| [[Club - Deportes]] | Golf, Tenis, Natación, Vela, Equitación |
| [[Club - Servicios]] | Eventos, Facturación, Acceso, POS |
| [[goliatt_pms]] | Property Management System |
| [[Otros Módulos]] | Nómina, Presupuesto, Bodega, Restaurante |

---

## Grafo de Dependencias (módulos propios)

```
account (Odoo base)
  └── co_accounting_extended
        ├── account_ledger_report
        ├── account_general_ledger
        ├── account_balance_sheet
        ├── account_profit_loss
        ├── account_aged_receivable
        ├── account_aged_payable
        ├── account_cash_flow
        └── goliatt_contabilidad
              └── co_bank_reconciliation

base / account
  └── club_core
        ├── club_golf
        ├── club_tennis
        ├── club_swimming
        ├── club_sailing
        ├── club_equestrian
        ├── club_events
        ├── club_guests
        ├── club_news
        ├── club_pqr
        ├── club_assembly
        ├── club_faq
        ├── club_job_offers
        ├── club_lost_found
        ├── club_object_loan
        ├── club_tournaments
        ├── club_affiliate_employees
        ├── club_affiliate_billing
        └── club_access_control
```

---

## Tags por módulo

- #contabilidad — módulos de contabilidad colombiana
- #reporte — reportes financieros
- #club — gestión de club
- #infraestructura — setup y DevOps

---

*Última actualización: 2026-04-13*
