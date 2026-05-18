# Image-Digest Autocomplete (Mint Form) — Design Spec

**Date:** 2026-05-18
**Author:** Manuel Caro (with Claude)
**Status:** Draft
**Spec type:** design spec
**Scope of work:** Replace the operator-mint form's free-text `image_sha256` field with a picker that autocompletes from recent `enterprise-v*` GHCR tags. Reduces transcription error (64-hex digests are easy to fat-finger) and reduces operator time per mint.

---

## 1. Goal

Today operator opens `/licenses/new`, copy-pastes the 64-character hex digest of the current `enterprise-v*` image from somewhere (CI Step Summary, GHCR UI, or memory). Easy to get wrong, no validation beyond regex. Replace with a dropdown that lists the 10 most recent `enterprise-v*` tags from GHCR with their digest + push date, plus a manual-entry fallback for edge cases.

## 2. Non-goals

- Not querying private GHCR. The `odoo-saas-odoo-enterprise` package can be public; the digest list is non-secret.
- Not autocompleting the customer_ref or any other field. Only image_sha256.
- Not validating that the digest currently exists in GHCR at mint time. Tag-vs-digest binding can drift (someone could delete the package version), but the digest is what's authoritative for license binding — once minted, the license points at the digest regardless.

## 3. Tenancy impact

None. GHCR API call is operator-side, returns public catalog data.

## 4. Data model changes

None. Optional: cache GHCR responses in a new `gh_package_versions` table to reduce API hits, but premature optimization for the current single-operator scale. Defer.

## 5. API surface

**New tRPC query `enterpriseLicenses.recentEnterpriseImages()`:**

Returns the 10 most recent `enterprise-v*` tagged versions of `ghcr.io/<owner>/odoo-saas-odoo-enterprise` as `{tag, digest, createdAt, sizeBytes}[]`.

Implementation:
- Call `GET https://api.github.com/users/${OWNER}/packages/container/odoo-saas-odoo-enterprise/versions` with optional GH token (env: `GITHUB_PACKAGES_TOKEN`; falls back to unauthenticated if package is public).
- Filter to entries with at least one tag matching `^enterprise-v.*` (regex).
- Map to `{tag: <matched-tag>, digest: <version.name without 'sha256:'>, createdAt: <version.created_at>, sizeBytes: <metadata.container.size or null>}`.
- Sort by createdAt desc, limit 10.
- Cache the result for 60 seconds (in-memory Map; per Vercel function instance — fine for low cardinality).

**Operator-only** procedure. Customer-facing surface doesn't need this.

## 6. Security model

GHCR API call goes out to github.com over HTTPS. Token (if used) reads packages only — minimal scope. No sensitive data returned.

If the call fails (network, rate limit, GitHub down), the procedure returns an empty list; the UI gracefully falls back to manual digest entry. No hard failure.

**Note on rate-limiting:** unauthenticated GitHub API is 60 req/hr/IP; with a token, 5000 req/hr. Operator-only surface + 60s cache = fine even without a token.

## 7. Test plan

**Unit (vitest):**
- Mocked GHCR response with 3 tagged versions + 5 untagged versions: result includes only the 3 with tags.
- Mocked response with `enterprise-v1` + `v1` (standard tag): only `enterprise-v1` makes the cut.
- Mocked 404 (package doesn't exist): returns empty list, no throw.
- Mocked rate-limit 403: returns empty list, logs warning.
- Cache hit: second call within 60s does NOT re-fetch.

**Integration:** none required; pure HTTP wrapping.

**E2E (Playwright):**
- `/licenses/new` → image_sha256 field is a combobox; opens dropdown; selecting an entry fills the field with the digest. Manual typing still works for edge cases.

## 8. Rollout plan

Single PR. Procedure additive; UI swap is replacing one `<Input>` with a `<Combobox>` from shadcn (already installed).

**Wave:** canary. Replaces the existing field; operator can still type a digest manually if they prefer or if the dropdown is empty.

**Rollback:** revert.

## 9. Observability

Logs each GHCR API call with `{cached: bool, count, duration_ms}`. No new alerts.

## 10. Open questions

1. **Public vs private package:** today `odoo-saas-odoo-enterprise` package is GHCR-private (default). Making it public is the right call (per the onboarding dry-run report) but is an operator action not yet taken. If still private when this lands, set `GITHUB_PACKAGES_TOKEN` in Vercel admin env (read:packages scope).
2. **Cross-org packages:** if the owner ever changes (e.g., from `remcaro-rgb` to a `goliatt-co` org), the query needs to be aware. Read GHCR_OWNER from env, fall back to `GITHUB_REPOSITORY_OWNER` if not set.
3. **Cache strategy:** in-memory Map cache is per-function-instance. With Vercel Fluid Compute reusing instances, cache hit rate should be decent. If it becomes a problem, move to Vercel Runtime Cache (per the runtime-cache skill).
4. **Tag filter strictness:** is `^enterprise-v.*` the right pattern? The runbook also allows `enterprise-<customer-slug>` tags (e.g., for a customer-specific build). Should those appear in the dropdown? Probably yes — operator picks the one bound to the customer they're minting for. Recommendation: include any tag matching `^enterprise-`.
