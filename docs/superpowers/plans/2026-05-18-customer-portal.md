# Customer Portal Implementation Plan

> **For agentic workers:** Execute task-by-task. Each task lands as one commit. All work in `/Volumes/SATECHI2TB/userfolder/Odoo-control-plane`, branch `agent/customer-portal`. Path alias `~/*` → `./app/*`. shadcn Button has NO `asChild` (base-ui variant); use `buttonVariants()` on `<Link>` + controlled-open pattern on dialogs.

**Goal:** Ship the customer-portal license self-service UI per `docs/superpowers/specs/2026-05-18-customer-portal-license-self-service-design.md`. Enterprise customers log in to apps/portal, see their license status + history + checks + downloadable install bundle.

**Architecture:** Server Components + Server Actions (no client tRPC). Layered auth: middleware → AuthGate `requireCustomer()` → `customerProcedure` (pins customer_ref into every WHERE clause).

**Tech Stack:** Next 16, React 19, tRPC v11, Drizzle, Clerk v6, Tailwind v4, shadcn/ui (base-ui variant), zod.

**Open-question decisions (locked):**
1. Customer identity: `customer_ref` free text (v1) — no schema migration.
2. Multi-license: 1:1 (latest license shown).
3. Bundle format: zip with `docker-compose.yml` + `.env.template` + `README.md`.
4. HMAC recovery: "contact support" message in UI.
5. Staleness alert: deferred to v2.

---

## Task 1: Bootstrap Tailwind v4 + shadcn in apps/portal + layout shell + sign-in/not-authorized

**Files (control plane):**
- `apps/portal/postcss.config.mjs` (new)
- `apps/portal/app/globals.css` (rewrite for Tailwind v4)
- `apps/portal/components.json` (new — shadcn config)
- `apps/portal/app/lib/utils.ts` (new — cn helper)
- `apps/portal/app/components/ui/*.tsx` (new — shadcn primitives: button, card, badge, dialog, alert-dialog, label, input, table, sonner)
- `apps/portal/app/components/app-shell.tsx` (new)
- `apps/portal/app/sign-in/[[...sign-in]]/page.tsx` (new)
- `apps/portal/app/not-authorized/page.tsx` (new)
- `apps/portal/app/layout.tsx` (modify: add Toaster, keep ClerkProvider)

Steps:
1. `cd apps/portal && pnpm add -D tailwindcss@^4 @tailwindcss/postcss postcss`
2. Write `postcss.config.mjs` exporting `{plugins:{'@tailwindcss/postcss':{}}}`
3. Rewrite `app/globals.css` to use `@import "tailwindcss"` + `@theme` block (use same neutral palette as admin)
4. `npx shadcn@latest init -d` then `npx shadcn@latest add table badge button input label dialog alert-dialog card sonner`
5. Fix shadcn placement (it lands under `app/components/ui/` automatically since the existing tsconfig uses `~/*` → `./app/*`)
6. Calendar.tsx may have the same `table` className issue admin had — fix if present
7. Write `app/components/app-shell.tsx` with sidebar (License · History · Checks · Bundle), Clerk UserButton
8. Write `app/sign-in/[[...sign-in]]/page.tsx` (mirror admin's pattern, `forceRedirectUrl="/license"`)
9. Write `app/not-authorized/page.tsx` (friendly card)
10. Modify `app/layout.tsx` to import `<Toaster />` from `~/components/ui/sonner`
11. Typecheck + commit + push

## Task 2: Backend — Session.customerRef + customerProcedure + customer-self router

**Files:**
- `packages/api/src/context.ts` (modify: add `customerRef: string | null` to Session)
- `packages/api/src/trpc.ts` (modify: add `customerProcedure`)
- `packages/api/src/routers/customer-self.ts` (new)
- `packages/api/src/routers/_app.ts` (modify: register customerSelf)
- `apps/portal/app/api/trpc/[trpc]/route.ts` (modify: resolve customerRef from Clerk publicMetadata)
- `apps/portal/app/lib/trpc-server.ts` (new — getServerCaller for customer scope)
- `apps/portal/app/lib/auth/customer-gate.ts` (new — requireCustomer())
- `packages/api/test/customer-self.test.ts` (new)

Steps:
1. Update `Session` type: add `customerRef: string | null`. Update `createContext`.
2. Add `customerProcedure` mirroring `operatorProcedure`: throws FORBIDDEN if `ctx.session?.customerRef` is null/empty.
3. Implement `customer-self.ts` with 4 procedures:
   - `myLicense()` — SELECT latest license WHERE customer_ref = ctx.session.customerRef
   - `myLicenseHistory({cursor?, limit?})` — paginated (use shared `paginationSchema`)
   - `myInstallBundle()` — return `{licenseId, authorityUrl, imageDigest, dockerComposeYaml, envTemplate, readme}` — Markdown of `docs/enterprise-customer-install.md` is too long for ship; v1 returns the inline-ready content
   - `myLicenseChecks({cursor?, limit?})` — audit_log filter
4. Register in `_app.ts` as `customerSelf`.
5. Modify portal's tRPC route handler to read Clerk `publicMetadata.customerRef` and pass it in `Session`.
6. Create portal's `trpc-server.ts` (mirror admin's) — getServerCaller cached via React.cache.
7. Create portal's `customer-gate.ts` (mirror admin's operator-gate) — `requireCustomer()` redirects to /not-authorized if customerRef unset.
8. Write tests for `customer-self.list` (3 tests: returns rows for authed customer, FORBIDDEN for unset customerRef, customerRef scoping)
9. Add `vitest.config.ts` to `packages/api` already exists. Run `pnpm --filter @odoo-saas/api test customer-self`.
10. Typecheck + commit + push.

## Task 3: Customer dashboard `/license` page

**Files:**
- `apps/portal/app/(customer)/layout.tsx` (new — calls requireCustomer + AppShell)
- `apps/portal/app/(customer)/license/page.tsx` (new — dashboard)
- `apps/portal/app/components/license-status-badge.tsx` (new — mirrors admin's)
- `apps/portal/app/components/license-detail-card.tsx` (new)
- `apps/portal/app/lib/license-status.ts` (new — same deriveLicenseStatus as admin)

Steps:
1. Create `(customer)` route group with operator-gate equivalent layout.
2. Reuse the deriveLicenseStatus + LicenseStatusBadge code from admin (different file path, same logic).
3. Build the dashboard page: server component, calls `myLicense()`, renders a Card with:
   - Customer ref (heading)
   - Status badge (active / grace / expired / revoked) + days-until-expiry
   - LICENSE_ID (with copy button — client island)
   - LICENSE_AUTHORITY_URL
   - ODOO_IMAGE_DIGEST
   - Expires + grace dates
   - Links to History · Checks · Bundle pages
4. Handle "no license found" case with a friendly empty state ("Contact your Goliatt operator to get a license issued").
5. Typecheck + commit + push.

## Task 4: Bundle download + history + checks pages

**Files:**
- `apps/portal/app/(customer)/license/bundle/page.tsx`
- `apps/portal/app/(customer)/license/bundle/[asset]/route.ts` (download endpoint for compose/env/README)
- `apps/portal/app/(customer)/license/history/page.tsx`
- `apps/portal/app/(customer)/license/checks/page.tsx`
- `apps/portal/app/components/license-history-table.tsx`
- `apps/portal/app/components/license-checks-table.tsx`
- `apps/portal/app/lib/bundle.ts` (helper that renders compose YAML + env template strings)

Steps:
1. Bundle page: shows the 3 download links — docker-compose.yml, .env.template, README.md. Plus the values inline (LICENSE_ID, image digest, etc.) for copy-paste.
2. `[asset]/route.ts` — generates the file on the fly from the latest license, returns appropriate Content-Disposition.
3. History page: paginated table using shared pagination cursor.
4. Checks page: paginated audit_log filter.
5. Typecheck + commit + push.

## Task 5: Bootstrap vitest in apps/portal + customer-portal action tests

**Files:**
- `apps/portal/vitest.config.ts`
- `apps/portal/test/license-status.test.ts`
- `apps/portal/test/bundle.test.ts`
- `apps/portal/package.json` (add test scripts)

Steps:
1. Mirror admin's vitest setup (jsdom env, `~` alias).
2. 6 deriveLicenseStatus tests (copy from admin).
3. 4 bundle tests (renders compose YAML with right LICENSE_ID, env template, README content includes support contact).
4. Run + commit + push.

## Task 6: Final integration + open PR

Steps:
1. Run full local CI parity: lint, typecheck, tests on both packages/api and apps/portal.
2. `git push -u origin agent/customer-portal`
3. `gh pr create` with body covering: spec link, design decisions, smoke walk-through checklist.
4. Wait for CI green. Address any preview build failures (likely env vars to copy to Preview).
5. Hand off the PR URL to the user.

---

**Estimated:** 6 tasks, ~1100 LOC, ~4 hours subagent-driven.

**Skip the user-review gate** per `/goal` directive; user has already approved by issuing the goal.
