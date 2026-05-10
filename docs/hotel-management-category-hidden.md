# Hide Hotel Management Category — Change Log

**Date:** 2026-05-06
**Database affected:** `odoo-club19`
**Module involved:** `goliatt_pms` (custom-addons/goliatt_pms)

## Context

The `goliatt_pms` module declares `'category': 'Hotel Management'` in its manifest
(`custom-addons/goliatt_pms/__manifest__.py:9`). When the module list was first
updated, Odoo auto-created an `ir.module.category` record named "Hotel Management"
with xml_id `base.module_category_hotel_management` (id=104 in `odoo-club19`).

The module was later marked `'installable': False` and is currently in state
`uninstalled`, so the category is orphaned but still visible as a filter chip in
the Apps page.

## Change applied

Set `visible = false` on the category record so the chip is hidden in the Apps
sidebar without deleting the row (deleting would risk FK side effects on
`ir_module_module`, `res_groups_privilege`, and `ir_module_category.parent_id`).

```sql
-- Run inside the odoo-db-1 container against the target database
UPDATE ir_module_category
SET visible = false
WHERE id = 104;  -- "Hotel Management"
```

Verification:

```text
 id  |       name       | visible
-----+------------------+---------
 104 | Hotel Management | f
```

## Other databases

Checked `odoo` and `odoo-club` — neither contains a "Hotel Management" category,
so no action was needed.

## Notes for future maintenance

- This change is database-only. It is **not** persisted in source code or in any
  module data file.
- The category will not be re-created automatically because `goliatt_pms` is
  `installable: False` and Odoo skips uninstallable modules during the module
  list scan.
- If `goliatt_pms` is ever re-enabled (`installable: True`), Odoo's auto-
  categorization will re-create the category and reset `visible` back to true on
  the existing row. To prevent that permanently, change the manifest line to
  something like `'category': 'Hidden'`:

  ```python
  # custom-addons/goliatt_pms/__manifest__.py
  'category': 'Hidden',
  ```

- Note: `custom-addons/goliatt_pms/security/pms_security.xml` also defines a
  category record with xml_id `goliatt_pms.module_category_pms` and name
  "Hotel Management". This record was never actually loaded (the module is
  uninstalled), but if the module is reinstalled in the future it would create
  a *second* "Hotel Management" category. Consider removing or renaming that
  record at the same time as any future re-enable.

## How to revert

```sql
UPDATE ir_module_category
SET visible = true
WHERE id = 104;
```
