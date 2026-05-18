# Renew Action + Image-Digest Autocomplete Implementation Plan

**Specs:**
- `docs/superpowers/specs/2026-05-18-renew-license-action-design.md`
- `docs/superpowers/specs/2026-05-18-image-digest-autocomplete-design.md`

**Branch:** `agent/renew-and-autocomplete` (control plane). Both features are small + touch the same `/licenses` UI surface; consolidating saves PR ceremony.

## Open-question decisions (locked)

### Renew (spec §10)
1. Copy `notes` old → new: **NO** (per recommendation). Fresh empty notes on the new license.
2. `allowed_modules`: **copy old → new** (immutable at renewal; operator uses manual revoke+mint escape hatch to change).
3. Auto-email customer: **manual (v1)**. v2 adds optional checkbox.
4. Renewing not-yet-expired license: **allowed**; dialog description warns about the period overlap.

### Autocomplete (spec §10)
1. Public vs private GHCR: assume PUBLIC for `odoo-saas-odoo-enterprise` (operator should already have flipped the visibility per the customer-onboarding dry-run report; if still private, set `GITHUB_PACKAGES_TOKEN` env var).
2. Cross-org: read `GHCR_OWNER` env var; fall back to `GITHUB_REPOSITORY_OWNER` then hardcode `remcaro-rgb`.
3. Cache: in-memory `Map<string, {fetchedAt: number, items: Item[]}>` keyed by owner string; 60 s TTL.
4. Tag filter: regex `^enterprise-` (broader than `enterprise-v*` — includes `enterprise-<customer-slug>`).

## Phase A — Backend (1 commit)

**Files:**
- `packages/api/src/routers/enterprise-licenses.ts` — add `renew` mutation (Drizzle transaction: SELECT old → UPDATE old.revokedAt → INSERT new copying customerRef/imageSha256/allowedModules → INSERT audit_log row `action='license.renew'` with `{oldLicenseId, newLicenseId, termDays, graceDays, reason}` payload). Throws NOT_FOUND if old missing, CONFLICT if already revoked.
- `packages/api/src/routers/enterprise-licenses.ts` — add `recentEnterpriseImages` query. Calls GHCR REST API for package versions filtered to tags matching `^enterprise-`. 60s in-memory cache keyed by owner. Operator-only.
- `packages/api/test/enterprise-licenses-list.test.ts` (or new test file) — 4-5 renew tests + 4 autocomplete tests.

## Phase B — Frontend (1 commit)

**Files:**
- `apps/admin/app/lib/actions/licenses.ts` — add `renewLicenseAction({oldLicenseId, termDays?, graceDays?, reason?})`. Same `{ok, error}` contract; on success returns `{newLicenseId}`.
- `apps/admin/app/components/renew-dialog.tsx` — controlled-open Dialog. Inputs: termDays (default 365), graceDays (default 14), reason (optional textarea). Submit → server action → router.push(`/licenses/${newLicenseId}`).
- `apps/admin/app/(operator)/licenses/[id]/page.tsx` — add `<RenewDialog licenseId={...} />` to the action bar (only show when not revoked, alongside RevokeDialog).
- `apps/admin/app/components/image-digest-combobox.tsx` — client island. Fetches recent images via `caller.enterpriseLicenses.recentEnterpriseImages()` lazy on open. Dropdown of `{tag, digest, createdAt}`. Manual-type fallback.
- `apps/admin/app/components/mint-license-form.tsx` — replace plain `<Input>` for imageSha256 with `<ImageDigestCombobox />`.
- `apps/admin/test/actions-licenses.test.ts` — extend with 3 renewLicenseAction tests.

## Phase C — Final integration + PR (1 commit if needed)

- Verify lint + typecheck + tests on both packages.
- Push branch + open PR.

## Implementation conventions (unchanged from prior PRs)

- Path alias `~/*` → `./app/*`.
- shadcn Button has no `asChild` (base-ui); controlled-open dialogs; `buttonVariants()` on `<Link>`.
- Server Components for reads; Server Actions for mutations.
- Reuse `paginationSchema` if any list endpoint added (not in scope this PR).
