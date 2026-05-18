# Admin CRUD Surfaces Implementation Plan

**Spec:** `docs/superpowers/specs/2026-05-18-admin-crud-surfaces-design.md`
**Branch:** `agent/admin-crud` (control plane)
**Plan style:** consolidated into one PR (4 surfaces share UI shell and backend; splitting would be 4× the PR ceremony for the same code).

## Open-question decisions (locked)

1. **Provision approval:** v1 simple single-click. N=2 gate is v2 spec when team grows past 1 operator.
2. **Tenant detail cross-references:** show subscription + 10 most-recent backups + 10 most-recent provisioning_jobs inline, with deep-links to filtered pages for "see all".
3. **CODEOWNERS:** defer per-surface split (solo operator; @remcaro-rgb owns everything per current `.github/CODEOWNERS`).
4. **Plan price changes retroactivity:** new-signups-only; existing subscriptions unaffected. UI shows "this affects N future signups; existing subs keep current pricing" before save. No retroactive migration logic.
5. **markUntrusted blast radius:** flips `state='untrusted'` on `tenant_backups` row + sets a new `quarantined_at` timestamp. Janitor cron with delete-after-30-days horizon is a v2 follow-up.

## Phase A — Backend (1 commit)

**Files:**
- `packages/api/src/routers/tenants.ts` — extend `list` with filters + cursor (currently no pagination); add `get`, `update`.
- `packages/api/src/routers/plans.ts` — add `get`, `update`, extend `list` with optional inactive filter.
- `packages/api/src/routers/tenant-backups.ts` (new) — `list`, `get`, `markUntrusted`. Register in `_app.ts`.
- `packages/db/src/schema.ts` — add `quarantined_at` nullable timestamp column to `tenant_backups`. Drizzle migration applied to Neon main + preview.
- Audit_log inserts on every mutation.
- Unit tests covering operator-gate, filter compilation, mutation contracts.

## Phase B — Tenant CRUD UI (1-2 commits)

- `app/(operator)/tenants/page.tsx` — list with filter bar (state + slug search).
- `app/(operator)/tenants/[id]/page.tsx` — detail card + subscription summary + recent backups (≤10) + recent jobs (≤10) sections.
- `app/components/tenant-state-badge.tsx`, `tenant-table.tsx`, `tenant-filters.tsx`.
- `lib/actions/tenants.ts` — `updateTenantAction` server action with `{ok,error}` contract.

## Phase C — Backup catalog UI (1 commit)

- `app/(operator)/backups/page.tsx` — list with tenant + type filters.
- `app/(operator)/backups/[id]/page.tsx` — detail showing s3_key, sha256, sizes, restore_tested_at.
- `app/components/backup-table.tsx`, `mark-untrusted-dialog.tsx`.

## Phase D — Plans CRUD UI (1 commit)

- `app/(operator)/plans/page.tsx` — list.
- `app/(operator)/plans/[code]/page.tsx` — detail + edit.
- `lib/actions/plans.ts` — `updatePlanAction` with confirm-by-typing-plan-code guard for price changes.

## Phase E — Manual provision UI (1 commit)

- `app/(operator)/tenants/new/page.tsx` — form: orgId, slug, tier, region, planId, adminUserEmail.
- `lib/actions/tenants.ts` — `provisionTenantAction` calling existing `tenants.provision` mutation.
- Displays workflow run id + link.

## Phase F — Sidebar + PR (1 commit)

- `app/components/app-shell.tsx` — add 4 new nav items.
- Local CI parity check.
- Push + open PR against control-plane main.

## Implementation conventions (carried from prior work this week)

- Path alias `~/*` → `./app/*` (NOT `@/*`).
- shadcn Button has no `asChild` (base-ui variant) — use `buttonVariants()` on `<Link>` + controlled-open on dialogs.
- Server Components for reads via `getServerCaller()`; Server Actions for mutations with `{ok, data} | {ok, error}` contract.
- Reuse shared `paginationSchema` + `decodeCursor` + `nextCursorFor` from `packages/api/src/lib/pagination.ts`.
- Three-layer auth: middleware → `requireOperator()` in `(operator)/layout.tsx` → `operatorProcedure` in tRPC. Defense-in-depth `requireOperator()` inside each server action.

## Out-of-scope (deferred)

- N=2 provision approval gate (v2 spec).
- Janitor cron for quarantined backups (v2 spec).
- Plan modules + plan_feature_flags editing UI (v2; current scope is just plan fields + prices).
- Backup restore action from UI (CLI-only forever per the spec).
- Tenant "drop" action (CLI-only forever per the spec).
