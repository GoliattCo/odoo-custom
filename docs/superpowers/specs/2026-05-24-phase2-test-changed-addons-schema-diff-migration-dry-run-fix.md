# Phase 2 — `test-changed-addons` + `schema-diff` + `migration-dry-run`

**Date:** 2026-05-24
**Author:** Manuel Caro
**Status:** In Review
**Spec type:** fix-brief (Phase 2 of `docs/2026-05-15-spec-driven-dev-plan.md` — items P2.5, P2.6, P2.8)
**Linked issue:** N/A — Phase 2 hardening continuation (companion to PRs #39, #40)
**Severity:** medium

---

## 1. Symptom

After PR #39 (lint-xml + manifest-lint + gitleaks) and PR #40 (trivy + test-writing runbook), three Phase 2 items remain:

1. **`test-addon` is hardcoded to `saas_tenant_gate`.** Tests in every other addon never run in CI today; their breakage surfaces only at install time on staging / prod.
2. **No schema-diff signal on PRs that touch model fields.** Reviewers have to read the diff line-by-line to spot field additions / removals.
3. **No migration-dry-run.** A PR that ships a model-schema change doesn't get its migration scripts exercised before merge; `odoo -u all` only runs at deploy time and surfaces failures too late.

## 2. Repro

1. Push a PR that adds a `def test_something(self): self.assertFalse(True)` to `custom-addons/club_news/tests/test_x.py`. CI is green — the test never runs. Merge → install on staging → late surface.
2. Push a PR that adds 3 `fields.Many2one(...)` declarations to a model. Reviewer must hand-scan the diff to know what changed.
3. Push a PR that renames a model field in a way that requires a migration script. The migration is never exercised in CI; surfaces only on `odoo -u all` at deploy.

## 3. Affected tenants & severity

- **Tenants impacted:** none directly (PR-time gates), but a regression that gets through these is a tenant-runtime incident.
- **Severity:** medium for `test-changed-addons` (catches real test failures), medium for `migration-dry-run` (catches migration script bugs), low for `schema-diff` (developer experience).

## 4. Root cause

All three are explicit Phase 2 roadmap deliverables not shipped in the initial push (see `docs/2026-05-15-spec-driven-dev-plan.md` §Phase 2). Today's audit confirms them as the remaining gaps (P2.5, P2.6, P2.8 respectively).

## 5. Proposed fix

### P2.5 — `test-changed-addons` (refactor `test-addon` + `test-addon-httpcase`)

Add a `detect-changed-addons` step that computes the comma-joined list of changed addons under `custom-addons/` from the PR/push range. Wire that list into `INIT_MODULES` (for `test-addon` stop-after-init smoke) and into `--test-tags '/<addon1>,/<addon2>,...'` (for `test-addon-httpcase` HttpCase suite).

When zero addons changed: both jobs no-op-pass (the "skip if no work" pattern).

### P2.6 — `schema-diff` (informational PR comment)

New `infra/scripts/schema_diff.py` walks every changed `custom-addons/*/models/**.py`, parses with `ast` to extract `class X(models.Model)` bodies and their `fields.<Type>(...)` declarations, diffs against `BASE_SHA`, and prints a markdown table per file of field additions (`+`) and removals (`−`). The CI job `schema-diff` runs the script and pipes the output to `gh pr comment`. Informational only — does not fail the build.

Scope is deliberately tight: only `+`/`−` per `_name` (or `_inherit` for classical-inheritance classes). Type changes (`Char` → `Text`) and metadata edits (`string=`, `default=`) are noisy and already visible in the standard diff viewer.

### P2.8 — `migration-dry-run`

After `test-addon-httpcase`, a new job that:
1. Builds the Odoo image (cached from prior jobs).
2. Installs the changed addons fresh into a CI-managed Postgres.
3. Runs `odoo -u all` against the same DB — forces every installed addon's migration scripts + XML re-loading to execute. Asserts a zero exit code.

This is the lightweight variant of P2.8 from the roadmap. The full variant ("clone a representative staging tenant's DB and run `-u all`") needs staging tenant credentials in CI; that's a deferred follow-up. The lightweight variant still catches migration-script syntax errors, XML reload regressions, and `_register_hook` / `_init_column` bugs — the most common breakage classes.

## 6. Regression test

CI itself is the test:
- `test-changed-addons`: PR adds a test to a non-`saas_tenant_gate` addon; CI runs the new test. Negative test: PR with zero addon changes runs the job and it no-op-passes.
- `schema-diff`: a separate test PR adds a field; the bot posts a comment with the `+` row. Not part of this PR; optional follow-up.
- `migration-dry-run`: pre-existing PRs (after this lands) run the new job; it passes on the unchanged tree.

## 7. Rollout

- Severity = medium → ride the next normal wave.
- No feature flag — pure CI additions / refactors.
- Expected outcomes:
  - 2 new GitHub Actions jobs (`schema-diff`, `migration-dry-run`); 2 existing jobs (`test-addon`, `test-addon-httpcase`) refactored to be change-scoped.
  - No latency change for PRs that don't touch addons or models — both `schema-diff` and `migration-dry-run` no-op-pass in <30s when their scope is empty.
  - Phase 2 completion: 9 of 10 items shipped or partial. P2.8 leaves a deferred follow-up for full staging-tenant migration dry-run (needs CI access to staging credentials).
