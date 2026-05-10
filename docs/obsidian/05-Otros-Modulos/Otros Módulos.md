# Otros Módulos

[[🗺️ Mapa del Proyecto]]

---

## Módulos Operacionales Colombia

### [[co_payroll]] — Nómina Colombiana
**Versión:** 19.0.1.0.0  
**Depends:** `hr`, `hr_contract_community`, `hr_attendance`, `account`, `mail`  
Liquidación de nómina con aportes parafiscales, prestaciones sociales y retención en la fuente según legislación colombiana.

### [[co_budget]] — Presupuestos
**Versión:** 19.0.1.0.0  
**Depends:** `account`, `analytic`, `mail`  
Gestión presupuestal con seguimiento de ejecución vs presupuesto.

### [[co_fixed_assets]] — Activos Fijos
**Versión:** 19.0.1.0.0  
**Depends:** `account`, `mail`  
Control de activos fijos: depreciación, revaluación, baja.

### [[co_exogena]] — Información Exógena DIAN
**Versión:** 19.0.1.0.0  
**Depends:** `account`, `l10n_co`  
Generación de reportes de información exógena para la DIAN (autoridad tributaria colombiana).

### [[co_warehouse_extended]] — Almacén Extendido
**Versión:** 19.0.1.0.0  
**Depends:** `stock`, `purchase`, `purchase_requisition`, `account`, `hr`  
Extensiones al módulo de inventario/almacén para Colombia: requisiciones, autorizaciones de compra.

### [[co_restaurant]] — Restaurante
**Versión:** 19.0.1.0.0  
**Depends:** `mrp`, `stock`, `product`, `uom`  
Gestión de restaurante: recetas, producción de platos, control de ingredientes.

---

## Módulos de Terceros / Base

### hr_contract_community
**Versión:** 19.0.1.0.0  
**Depends:** `hr`  
Contratos de trabajo para edición Community (base para [[co_payroll]]).

---

## Property Management

### [[goliatt_pms]] — Goliatt PMS
**Versión:** 19.0.2.0.0  
**Depends:** `base`, `mail`, `account`, `product`, `stock`  
Sistema de gestión de propiedades (Property Management System).
