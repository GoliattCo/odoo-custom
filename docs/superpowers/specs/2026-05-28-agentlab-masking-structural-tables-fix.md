# Agentlab masking — never mask Odoo ORM-structural metadata tables

**Date:** 2026-05-28
**Author:** Manuel Caro
**Status:** In Review
**Spec type:** fix-brief (follows §2.5 of `docs/2026-05-15-spec-driven-dev-plan.md`)
**Linked issue:** #140
**Severity:** high

---

## 1. Symptom

`migration-dry-run-staging` reaches `odoo -u all` (after the #137/#139
pg_dump fix) and crashes:

```
KeyError: 'MASKED:89c9a034e5ec'
odoo.tools.convert.ParseError: while parsing .../base/data/res_bank.xml:5
<record id="res_bank_1" model="res.bank">
```

## 2. Repro

1. Restore + mask a tenant snapshot into agentlab (the daily-restore
   pipeline runs `infra/agentlab/mask_prod_data.py`).
2. Run `odoo -u all` against the masked DB (the migration dry-run does
   exactly this).
3. Loading the core `base/data/res_bank.xml` resolves xml-id
   `base.res_bank_1` via `ir_model_data`, reads its `model` column —
   now `MASKED:<hash>` — and `registry['MASKED:...']` raises `KeyError`.

**Reproduced on:** migration-dry-run-staging run `26569298273`.

## 3. Affected tenants & severity

- **Tenants impacted:** none directly (agentlab/CI only).
- **Severity:** high — every masked snapshot is unloadable by any module
  upgrade, so the migration safety net stays offline and any restore-based
  upgrade testing on masked data is broken. No prod migration defect is
  implied.

## 4. Root cause

`mask_prod_data.py` masks every column that is not in `mask-allowlist.yml`
(deny-all-but-allowlist). The Odoo ORM-structural metadata tables are not
allowlisted, so their short-string columns get the hashing `string`
strategy (`'MASKED:' || substr(md5(col),1,12)`).

`ir_model_data.model` is a Char field → classified `string` → hashed. The
`(module, name)` columns happen to be spared because they sit in a UNIQUE
index (the existing `_load_unique_columns` skip), but `model` is not part
of any unique index, so nothing protected it. A *running* Odoo tolerates
masked metadata (it doesn't re-resolve xml-ids at runtime), which is why
this stayed hidden until a `-u all`.

`infra/agentlab/mask_prod_data.py` — the per-column masking loop had no
notion of structural tables.

## 5. Proposed fix

Add an explicit structural-table skip:

- New constant `_STRUCTURAL_TABLES` + pure helper `is_structural_table()`
  covering `ir_model_data`, `ir_model`, `ir_model_fields`,
  `ir_model_fields_selection`, `ir_model_relation`, `ir_model_constraint`,
  `ir_module_module`, `ir_module_module_dependency`.
- Skip those tables in both the type-strategy pass and the deny-list pass
  (new `structural_skipped_columns` metric), and in `sample_audit` (a
  table declared non-PII shouldn't then fail the PII audit).

Deliberately an **explicit list, not a blanket `ir_*` skip**: other `ir_`
tables carry PII or secrets and must keep being masked (`ir_attachment`
blobs/filenames, `ir_mail_server` smtp creds, `ir_config_parameter`
values, `ir_logging`).

```python
_STRUCTURAL_TABLES = frozenset({
    "ir_model_data", "ir_model", "ir_model_fields",
    "ir_model_fields_selection", "ir_model_relation",
    "ir_model_constraint", "ir_module_module",
    "ir_module_module_dependency",
})

def is_structural_table(table: str) -> bool:
    return table in _STRUCTURAL_TABLES
```

## 6. Regression test

`infra/agentlab/tests/test_masking.py`:
- `is_structural_table()` returns True for each structural table and False
  for PII-bearing `ir_` tables (`ir_attachment`, `ir_mail_server`,
  `ir_config_parameter`, `ir_logging`) and ordinary tenant tables.
- A guard asserting `classify_column('ir_model_data','model',...)` still
  returns `string` — i.e. the classifier would mask it, so the
  structural-table skip stays load-bearing.

The DB-layer skip is additionally covered end-to-end by the
agentlab-daily-restore dry-run + the next migration-dry-run-staging run.

## 7. Rollout

- Severity = high → fix now (this PR).
- **Security note:** this touches the masking trust boundary. The change
  *reduces* what is masked, so it warrants security-lead review. It is
  framed as masker *logic* (a structural-table skip), not a
  `mask-allowlist.yml` exception — but if security prefers the allowlist
  mechanism (per its 2-reviewer rule), the same tables can be expressed
  there instead. The excluded tables hold framework definitions only and
  carry no tenant PII.
- Verification caveat: the unit tests run in CI ("Agentlab masking unit
  tests"); the full pipeline + `-u all` proof comes from the post-merge
  agentlab-daily-restore and migration-dry-run-staging runs.
