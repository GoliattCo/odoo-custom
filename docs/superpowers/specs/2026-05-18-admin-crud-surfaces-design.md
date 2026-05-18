# Admin CRUD Surfaces (Tenant / Plan / Manual Provision / Backup Catalog) — Design Spec

**Date:** 2026-05-18
**Author:** Manuel Caro (with Claude)
**Status:** Draft
**Spec type:** design spec
**Scope of work:** Four operator UI surfaces inside `apps/admin` that the hello-world page promised "land in later phases": tenant CRUD, plan CRUD, manual provision dashboard, backup catalog viewer. Each is independently shippable; this spec covers the shared shell + the four surfaces' design at a high level. Each surface gets its own implementation plan when its turn comes.

---

## 1. Goal

Round out the operator console so all Phase 1+ control-plane state is visible/manageable via the browser:

| Surface | Replaces today |
|---|---|
| Tenant CRUD (`/tenants`) | direct SQL or `tenants` tRPC procedure via curl |
| Plan CRUD (`/plans`) | direct SQL |
| Manual provision (`/tenants/new`) | tRPC `tenants.provision` mutation triggered via curl + Clerk session |
| Backup catalog viewer (`/backups`) | direct SQL on `tenant_backups` table |

All four follow the same architecture established by the license-management UI (Server Components for reads + Server Actions for mutations, Tailwind v4 + shadcn/ui, `~/*` alias).

## 2. Non-goals

- Not redesigning the underlying schemas. These surfaces are CRUD over existing tables.
- Not building observability dashboards (deferred to a separate "ops dashboards" spec — Better Stack integration per ADR-0003).
- Not adding any customer-portal surface (covered by [the customer-portal spec](./2026-05-18-customer-portal-license-self-service-design.md)).
- Not auto-deploying tenants from the UI (the manual provision dashboard is operator-driven; auto-provision happens via the existing signup flow in the portal).
- Not exposing destructive "drop tenant" from the UI — that's CLI-only forever, with manual operator approval.

## 3. Tenancy impact

These are operator-only surfaces over control-plane tables. No per-tenant data is touched directly (except the backup catalog, which lists per-tenant backup metadata but no payload). Tenancy isolation: every read/write goes through operator-gated tRPC procedures; same defense-in-depth as the license-management UI.

The backup catalog viewer SHOWS per-tenant data (backup metadata: tenant id, sha256, sizes, S3 key, KMS arn). Operator already has read access to these via Neon; this UI is presentation only.

## 4. Data model changes

**None for the four surfaces.** Tables involved: `tenants`, `plans`, `plan_modules`, `plan_feature_flags`, `subscriptions`, `tenant_backups`, `tenant_dek`. All exist.

Possible additive change later: a `tenant_admin_notes` table for operator-side scratch notes on a tenant (similar to `enterprise_licenses.notes`). Defer.

## 5. API surface

**Existing tRPC routers reused (mostly unchanged):**
- `tenants.list` / `tenants.get` / `tenants.provision` / `tenants.markUntrusted` (if not exposed, add it operator-gated)
- `plans.list` / `plans.create` / `plans.priceForCountry`

**Extended on the same backward-compat pattern as `enterpriseLicenses.list`:**
- `tenants.list` — add cursor pagination + status filter (active / pending / suspended / archived).
- `plans.list` — add cursor pagination, drop the implicit "active only" filter as a default-but-overridable flag.

**New tRPC procedures:**
- `tenants.update({ id, updates: { state?, planId?, notes? } })` — operator-only.
- `plans.update({ code, updates: { ... } })` — operator-only. Plan schema changes are sensitive; emits an audit row.
- `tenantBackups.list({ tenantId?, type?, from?, to?, cursor?, limit? })` — operator-only read.
- `tenantBackups.get({ id })` — operator-only.
- `tenantBackups.markUntrusted({ id, reason })` — flips `state='untrusted'` on rows the restore-drill couldn't validate (already partly implemented; UI wires it).

**Server actions:** parallel to the license-management ones; same `{ok, data} | {ok, error}` contract.

## 6. Security model

Same three-layer pattern as the license-management UI:
1. Clerk middleware (`proxy.ts`).
2. Layout-level `requireOperator()` in `app/(operator)/layout.tsx` — already in place.
3. tRPC `operatorProcedure` on every read/write.
4. Server actions repeat the gate.

**Provision endpoint has higher blast radius** than the others (creates infrastructure on Railway/Fly that's hard to undo). Future enhancement: require N=2 operator approvals for `tenants.provision` via a "pending → approved → ran" state machine. Out of scope for v1; document as a v2 spec.

**Backup catalog viewer:** read-only by default. `markUntrusted` is the only mutation; mostly used during a quarterly restore drill. Audit-logged.

## 7. Test plan

Per-surface vitest + Playwright matching the license-management UI's pattern. Reuse the test infra already in place. Each surface ships with:

- Unit: derived-state helpers (e.g., tenant status badge derivation), filter coercion, server action contracts.
- Integration: 1 happy-path round-trip per mutation on ephemeral Neon (gated on item 16 landing).
- E2E: 1 spec per surface for the core flow (list → detail → mutate → assert).

## 8. Rollout plan

**Each surface is its own PR**, in order:

1. **Tenant CRUD** (`/tenants` + `/tenants/[id]`) — highest-value, most-needed today. Read-only first; add update mutation in PR 1.1.
2. **Backup catalog viewer** (`/backups`) — independent of tenant CRUD, useful in restore drills.
3. **Plan CRUD** (`/plans`) — lowest churn (plans rarely change); ship last.
4. **Manual provision** (`/tenants/new`) — depends on tenant CRUD shipping first. Gated behind a feature flag if the N=2 approval enhancement isn't shipped at the same time.

Each PR gates its own surface; layout shell already exists.

## 9. Observability

Same as license-management UI: server-action structured logs to Vercel logs; audit_log row is canonical. No new metrics or alerts.

## 10. Open questions

1. **`/tenants/new` provision approval flow:** do we land it as a simple "click Provision now" or with the N=2 approval gate? N=2 is safer (provisioning cost real $$, hard to undo) but slows the operator flow. Recommendation: v1 = simple; v2 = approval gate when the team grows past one operator.
2. **Plan CRUD blast radius:** changing a plan's `price_*_cents` mid-billing-cycle is hazardous — does it apply to existing subscriptions retroactively, or only new signups? Document the answer in the UI before letting the operator change live plan rows. Recommendation: warn on save; require typing the plan code to confirm.
3. **Backup catalog `markUntrusted`:** flips a flag the restore-drill workflow respects, but does it actually QUARANTINE the row? E.g., should it DELETE the S3 object? Recommendation: no delete; quarantine flag + a `delete_at` timestamp set 30 days in the future; a janitor cron picks them up. (Mirror the license-expiry-reminder cron pattern.)
4. **Per-surface CODEOWNERS:** tenant + plan CRUD probably wants `security-leads` review; backup catalog can be `prod-deployers`-only. Update `.github/CODEOWNERS` when these ship.
5. **Tenant detail page width of scope:** beyond core fields, should it show the tenant's recent license_checks, recent backups, recent provisioning_jobs? Each is another tRPC call. Recommendation: yes, on the tenant detail page — operator wants one-stop visibility per tenant. Pagination cursors limit each section to ~10 entries with "See all in /backups?tenant=…" deep-link.
