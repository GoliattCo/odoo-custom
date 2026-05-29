# Action-table masking remediation — cleanup workflow + base-table skip fix

**Date:** 2026-05-29
**Author:** Manuel Caro
**Status:** In Review
**Spec type:** fix-brief (follows §2.5 of `docs/2026-05-15-spec-driven-dev-plan.md`)
**Linked issue:** #142
**Severity:** high

---

## 1. Symptom

After the masking-scope (#141/#144) and reliability (#145/#149) fixes, a real
re-mask + `migration-dry-run-staging` finally reached `odoo -u all` and still
failed:

```
ValueError: Wrong value for ir.ui.menu.action: 'MASKED:...,5'
while parsing .../base/views/decimal_precision_views.xml:36
```

## 2. Repro / root cause

`ir.ui.menu.action` is a Reference (`"<model>,<id>"`); at `-u all` Odoo builds
it from the target action's `type` field — `f"{action.type},{action.id}"`.
`ir_act_window.type` (and siblings) hold `MASKED:<hash>`, so the value becomes
`"MASKED:...,5"` and rejects.

Established (issue #142, airtight): the masker's structural skip for these
tables is correct (`structural_skipped` rose to 287/308; the smoke only scans
tables the masker also skips), so **this run did not mask them** — the
`MASKED:` values are **pre-existing in the restored source** (staging carries
historical masker output from before the framework-table skip existed). The
masker can't un-hash them.

Plus a related defect found while remediating: `_STRUCTURAL_TABLES` listed
`ir_actions_actions`, but the base `ir.actions.actions` model's table is
**`ir_actions`** — so the base action table was **not** being skipped and
could be masked by current runs.

## 3. Affected tenants & severity

- **Tenants impacted:** none in prod (agentlab/CI), but masked snapshots are
  unloadable by `-u all`, so the migration safety net stays offline.
- **Severity:** high.

## 4. Fix

Two parts — a data remediation tool and a masker correctness fix.

### a. Masker: skip the real base table

`infra/agentlab/mask_prod_data.py` — `_STRUCTURAL_TABLES`: replace the
non-existent `ir_actions_actions` with the real base table `ir_actions`, so
the base action table stops being masked going forward (+ test updated).

### b. One-shot cleanup workflow (data remediation)

The masker can't clean pre-existing pollution, so a `workflow_dispatch` job
resets the constant-valued columns in place:

- `.github/workflows/clean-action-masking.yml` — opens the existing flyctl
  proxy (reusing `FLY_AGENTLAB_TOKEN` + `AGENTLAB_DSN`/`STAGING_PG_DSN`), then
  runs the SQL per tenant DB. Inputs: `target` (agentlab|staging),
  `tenant_filter`, `dry_run` (**default true** → discovery only), and a
  `confirm` gate (must equal the target name to apply). Credentials stay in
  `PG*` env (never argv); psql uses keepalives (per #149).
- `infra/agentlab/sql/discover_action_masking.sql` — read-only; reports every
  polluted `ir_act_*` / `ir_actions` text column with counts, plus an
  `ir_actions` id-mapping integrity check (masked/unique/unmapped/multi) that
  proves the base-table reconstruction below is safe before any write.
- `infra/agentlab/sql/clean_action_masking.sql` — resets the concrete
  `ir_act_*` tables' `type` to the fixed per-table constant
  (`ir.actions.act_window`, …) and `binding_type` / `binding_view_types` to
  Odoo-18 defaults; then reconstructs the **base `ir_actions`** row's `type`
  by joining each masked row to the concrete table sharing its `id` (this is
  the column `ir.ui.menu.action` is built from — the real `-u all` breaker).
  Masked rows only.

Discovery on agentlab confirmed the approach: `acmesas2` and `demo` each had
534 masked cells (incl. `ir_actions`: 89 in each of type/binding_type/
binding_view_types), the id-mapping was a clean 1:1 (`masked=89 unique=89
unmapped=0 multi=0`), and the post-apply verify read 0 across all three DBs.

The workflow also mirrors each DB's discovery/verify output into a `::notice::`
annotation, so results are retrievable via the checks API on runners where the
log archive can't be downloaded.

## 5. Regression test

`infra/agentlab/tests/test_masking.py` (128 passing) — structural set now
asserts `ir_actions` (not `ir_actions_actions`). The DB-layer SQL/workflow is
validated by the dispatch run itself (no live PG in unit tests).

## 6. Rollout / usage

1. **agentlab, dry-run** (discovery) → confirm polluted columns + id-mapping.
   **DONE** — 3 DBs, two polluted (534 cells each), mapping clean.
2. **agentlab, apply**: `dry_run=false confirm=agentlab`. **DONE** — verify
   reads 0 on all three DBs.
3. **staging, apply**: `dry_run=false confirm=staging` → permanent source fix,
   then re-run `migration-dry-run-staging` to validate `-u all` clears
   (closes #142's validation aspect).
4. **Caveat:** masked **per-row** columns the reset can't reconstruct
   (`*.res_model`, `*.name`, or any `ir_actions` row with `unmapped>0` in the
   diagnostic) need `odoo -u base --stop-after-init` on the source or a
   re-seed from clean prod. The agentlab run showed `unmapped=0`, so none
   applied there.
- Security-adjacent (writes to shared DBs) → security/ops review; the
  dry-run default + confirm gate keep accidental mutation out.
- Verification caveat: not runnable from the automation sandbox (no Fly);
  proven by the dispatch run.
