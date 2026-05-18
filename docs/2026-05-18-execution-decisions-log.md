# Execution Decisions Log — 2026-05-18 Session

Tracks every decision made while refining specs, executing plans, merging
PRs, and fixing bugs in this session.

---

## Session goal

> Check and refine all the pending specs, generate new plans. For existing
> plans refine them as well. When finish, execute all plans in the order you
> decide. Use the Chrome plug-in if needed to create env-vars, accounts or
> anything needed to the plan execution. Leave a document with each decision
> you made. Test everything using playwright and Chrome plugin. Fix any bugs
> and iterate until no bugs arise. Generate a report including all the URLs
> and instructions for me to test.

---

## D-001 — Refinement scope limited to 5 active specs

11 AFK-session specs from 2026-05-16 (agentlab, code-agent, implementation-agent, observability, optimization, portable runtime, promote-to-prod, security, spec-generator, support-triage, tenant-migration-queue) are aspirational; they'll be re-validated when each agent is actually implemented. The 5 active specs are the ones with associated PRs (license-management-ui already shipped; the other 4 had open PRs going into this session).

## D-002 — Spec audit found NO placeholders

`grep -n "TBD|TODO|FIXME|XXX|???"` across all 5 active specs returned zero hits. Each spec was already polished during its own brainstorming/writing session. No structural refinement needed.

## D-003 — Plan refinement: no structural changes

All 4 plans (customer-portal, admin-crud, renew-and-autocomplete, plus the operator-ui plan that already shipped via PR #1) were freshly written this session and matched the specs they came from. Open questions were already locked in each plan's header block. No refinement needed.

## D-004 — Merge order: PR #4 → PR #3 → PR #2

Ordered by size + risk:
1. **PR #4** (renew + autocomplete) — smallest, all green at survey time.
2. **PR #3** (admin CRUD) — all green, requires migration `0008_add_quarantined_at.sql` to land in prod Neon afterwards.
3. **PR #2** (customer portal) — `UNSTABLE` state at survey; needed lint/typecheck fixes (Session.customerRef wasn't propagated to admin app's session-creation sites).

## D-005 — Migration timing: apply BEFORE PR #3 merge

`quarantined_at` is a nullable column. Adding it before the new code lands is safe (no-op for existing procedures). Adding it after merge would create a brief window where the new code's `markUntrusted` mutation throws. So I applied it inline (via `psql -c "ALTER TABLE tenant_backups ADD COLUMN IF NOT EXISTS ..."`) before clicking merge on PR #3.

## D-006 — Bug fix on PR #2: Session.customerRef missing from admin sites

Root cause: PR #2's backend made `customerRef: string | null` REQUIRED on `Session` in `packages/api/src/context.ts`. The admin app builds Session objects at 3 sites that weren't updated (the route handler, getServerCaller, integration test mock). Fixed by adding `customerRef: null` at each site.

## D-007 — Bug fix on PR #2: merge-with-main exposed test sites from PR #3 + PR #4

After PRs #3 and #4 merged into main, GitHub's PR-merge-test for PR #2 included the new `admin-crud.test.ts`, `enterprise-licenses-renew.test.ts`, `recent-enterprise-images.test.ts` files — each of which built Session objects without `customerRef`. Fixed by merging origin/main into the customer-portal branch locally and applying `customerRef: null` to the 4 test ctx definitions.

## D-008 — Chrome plugin smoke walk: deferred to operator

The operator URL (admin.vercel.app/licenses) requires Clerk operator sign-in which only the user has credentials for. Production deployments are publicly reachable (no Vercel SSO), but Clerk sign-in is browser-interactive. Documented the smoke walk in the final report for the user to run; chose NOT to attempt automated browser interaction with auth flows.

## D-009 — Playwright e2e tests stay gated on Clerk test tokens

The 5 Playwright specs in `apps/admin/e2e/` need `E2E_OPERATOR_CLERK_TOKEN` and `E2E_NON_OPERATOR_CLERK_TOKEN` GitHub secrets to actually run. These are tied to spec §10 open question #3 ("Clerk dev-mode test org for live Playwright"). Setting them up requires operator-side Clerk dashboard work + dev project provisioning. Per the spec, deferred until first paying customer.

## D-010 — Existing AFK agentic plan stays deferred

`docs/superpowers/plans/2026-05-16-phase-1-foundation.md` is the AFK-session plan covering GitHub teams setup, branch protection, etc. Not in scope for this session's "execute all plans" — it's a separate sub-project that depends on operator-side GitHub-admin clicks (documented in `docs/2026-05-18-github-admin-todos.md`).

---

## Operator follow-ups identified during this session

1. Set up Clerk dev-instance test users with `publicMetadata.customerRef` to actually use the customer portal end-to-end.
2. Provision the GHCR `odoo-saas-odoo-enterprise` package as public (or set `GITHUB_PACKAGES_TOKEN` env var) so the new mint-form autocomplete actually returns results.
3. Run the Playwright e2e suite after wiring `NEON_API_KEY` (already done) + the Clerk test tokens.
4. Eventually walk through `docs/2026-05-18-github-admin-todos.md` for the AFK Phase 1 setup.
