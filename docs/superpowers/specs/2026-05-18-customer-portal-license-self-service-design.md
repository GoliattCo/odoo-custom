# Customer Portal — License Self-Service — Design Spec

**Date:** 2026-05-18
**Author:** Manuel Caro (with Claude)
**Status:** Draft
**Spec type:** design spec (follows §2.4 of `docs/2026-05-15-spec-driven-dev-plan.md`)
**Scope of work:** First customer-facing UI slice in `apps/portal` of the control plane. Enterprise self-host customers log in, see their own license status, download install bundle artifacts, see expiry/renewal info. Counterpart to the operator's `/licenses` dashboard (already shipped 2026-05-17).

---

## 1. Goal

Give enterprise self-host customers a self-service dashboard for their license: status (active/grace/expired/revoked), upcoming expiry, install-bundle download (docker-compose template pre-filled with their LICENSE_ID + LICENSE_AUTHORITY_URL + image digest), past renewal history. Reduces operator handhold time on the post-onboarding "what's my LICENSE_ID again?" / "when does this expire?" tickets, and gives the customer a place to verify their license is healthy from Goliatt's perspective without having to email support.

## 2. Non-goals

- Customer cannot mint / revoke / renew their own license (operator-only via admin app). Self-service ALWAYS gated by operator.
- Customer cannot view the LICENSE-SIGNING private key, the per-customer HMAC secret in cleartext after initial issuance, or any other operator secret.
- No customer support chat / ticket portal — out of scope for v1.
- No multi-license-per-customer UI; current model is 1:1. When that changes (a customer with multiple self-host instances), add a license picker — defer until first such customer.
- No license-check telemetry visible to the customer (they can see their own `audit_log` entries for `license.check` actions; that's it).

## 3. Tenancy impact

**Per-customer data isolation is mandatory.** The portal queries `enterprise_licenses` filtered by `customer_ref = <authenticated customer's identifier>`. The customer can only see THEIR rows. Any cross-customer leak here would be a security incident.

Tenancy enforcement happens at the tRPC procedure layer via a new `customerProcedure` (mirror of `operatorProcedure`) that asserts `ctx.session.customerRef` is set and pins all queries to `WHERE customer_ref = $session.customerRef`. Operator users that hit portal endpoints get rejected (operator-only is admin app; customer-only is portal).

`audit_log` rows visible to customers: only those with `target_type='license'` AND `target_id` matching one of the customer's licenses. Other namespaces (tenant.*, backup.*, email.*) are operator-internal and never exposed.

## 4. Data model changes

**Add `customer_id` mapping to `enterprise_licenses`** (optional column at first). Today `customer_ref` is free-form text (typically email); to support multiple-licenses-per-customer plus a clean customer identity for Clerk session resolution, link to a new (or existing) `customers` table. v1 can ship with `customer_ref` as the join key (still text), but the Drizzle schema should grow a forward-compatible nullable `customer_id UUID` column referencing `customers.id`.

Decision deferred to brainstorm: add the column now (auto-populates on next mint based on customer_ref match) or land the customer identity schema as a prerequisite.

## 5. API surface

**New tRPC router `packages/api/src/routers/customer-self.ts`:**

- `customerSelf.myLicense()` — query, customer-only. Returns the most-recent active OR most-recent overall license bound to the authed customer's ref. Includes derived status + days-until-expiry.
- `customerSelf.myLicenseHistory({ limit?, cursor? })` — query, paginated.
- `customerSelf.myInstallBundle()` — query. Returns the pre-filled docker-compose template content + .env template values (LICENSE_ID, LICENSE_AUTHORITY_URL, ODOO_IMAGE_DIGEST). Does NOT include the per-customer HMAC secret (the operator delivered that out-of-band at onboarding; the portal cannot re-display it).
- `customerSelf.myLicenseChecks({ limit?, cursor? })` — query. Recent `audit_log` rows where `action='license.check' AND target_id IN (customer's license ids)`. Lets the customer see "is my install actually calling home and being validated".

No new HTTP routes; existing `/api/internal/license/check` stays HMAC-gated for the addon, not changed.

**New `customerProcedure` in `packages/api/src/trpc.ts`** that gates on `ctx.session.role === 'customer'` and pins `ctx.session.customerRef` into every query's WHERE clause.

## 6. Security model

**Authentication:** Clerk in `apps/portal` (already wired for the existing signup/onboarding flow). Customers sign in via the same Clerk org as operators but with a different `publicMetadata.role` value (`'customer'` instead of `'operator'`).

**Authorization layers (mirror of admin app):**
1. `proxy.ts` middleware — Clerk session required.
2. Layout-level `requireCustomer()` server-side gate — reads role, asserts customer, redirects operators to admin app + non-roled users to `/not-authorized`.
3. `customerProcedure` in tRPC — same check + extracts `customerRef` from Clerk metadata.
4. Server actions repeat the gate as defense-in-depth.

**Customer-ref binding:** When the operator mints a license via the admin app, they enter `customer_ref` as free text (typically email). The customer's Clerk user must have `publicMetadata.customerRef` populated to the SAME value — operator does this manually via Clerk dashboard when sending the install bundle. Mismatch = customer sees an empty dashboard.

**Sensitive data exposure:** customer sees their own LICENSE_ID (already shared with them out-of-band; not new exposure), image digest (public — it's in their image manifest), expiry dates. Never sees other customers' data, the Ed25519 private key, the per-customer HMAC secret in cleartext, or any operator audit log entries beyond their own license events.

**Tenancy-isolation argument:** Every customer-facing query passes through `customerProcedure` which appends `eq(enterpriseLicenses.customerRef, ctx.session.customerRef)` to the Drizzle WHERE clause. No procedure exposes a "list all" path. Unit + integration tests assert that bypassing the customerRef filter is impossible from the customer surface (the procedure signature doesn't accept `customerRef` as an input).

## 7. Test plan

**Unit (vitest):**
- `customerProcedure` rejects requests without `ctx.session.role === 'customer'`.
- `myLicense()` query filter compiles to a WHERE clause containing `customerRef = $session.customerRef` even when the caller tries to override via cookie/header tampering.
- `myInstallBundle()` does NOT include any HMAC secret in its return shape.

**Integration (ephemeral Neon branch):**
- Two customers (`alpha@`, `beta@`) each with a license. Authed as alpha, `myLicense()` returns only alpha's row; `myLicenseHistory()` excludes beta's. Audit-log view excludes beta's `license.check` entries.

**E2E (Playwright on portal):**
- Customer signs in → lands on portal dashboard → sees their license status.
- Download install bundle → file contents match the docker-compose template.
- Operator signs into portal accidentally → redirected to admin.

**Adversarial:**
- POST a fake `customerRef` in a tRPC procedure input → input schema doesn't accept it; ignored.
- Brute-force enumerate other customer license IDs by changing URL fragments → all surfaces are scoped via session, no license_id-driven endpoints.

## 8. Rollout plan

**Wave:** canary. Portal app already exists with signup/onboarding routes; this adds a new authenticated section. No public traffic until we tell a customer.

**Sequence:**
1. Add `customerProcedure` + new tRPC router (additive). Deploy portal.
2. Add `app/(customer)/` route group with layout + dashboard page. Deploy.
3. Add install-bundle + history + license-checks pages. Deploy.
4. Update Clerk users to have `publicMetadata.customerRef`. (Manual; one customer.)
5. Hand the first customer their portal URL.

Each step is its own PR, independently revertible. `customerProcedure` shouldn't ship the same PR as the UI — verify the procedure works in isolation first.

**Migration cost:** zero. Schema column add (if we land `customer_id`) is additive nullable; backfill is a one-off script.

**Rollback path:** revert the relevant PR. The operator surface is unaffected.

## 9. Observability

- Every `customerSelf.*` procedure logs `{customerRef, procedure, ok, duration_ms}` to Vercel logs.
- No PII in logs beyond customer_ref (which is already an email).
- Optional alert: customer's most-recent `license.check` audit entry is >24 h old → may indicate the customer's install is offline. v2 nice-to-have, not v1.

## 10. Open questions

1. **Customer identity model:** stick with `customer_ref` as free text (current), or introduce a `customers` table with UUIDs and `customer_id FK` on `enterprise_licenses`? The latter is more correct long-term but adds migration scope. Recommendation: ship v1 with `customer_ref` for simplicity; track schema evolution as a v2 item.
2. **Multi-license-per-customer support:** v1 assumes 1:1. When the first customer has 2 licenses (e.g., two separate Odoo installations), the dashboard needs a picker. Defer until that customer exists.
3. **Self-service install-bundle download:** what's the right format? Single docker-compose.yml? A tar with both the compose and a README? Recommendation: zip with `docker-compose.yml` + `.env.template` + `README.md` (the customer install README from `docs/enterprise-customer-install.md`).
4. **HMAC secret recovery:** if a customer loses their `SAAS_PROVISIONING_SECRET`, can they self-serve a new one? Probably not — that's a security-sensitive operation that should require operator action. Document as "contact support".
5. **Customer-side license-check failure alerts:** when a customer's install fails to call home for >X hours, should they get an automatic email? Or only the operator (current behavior via license-expiry-reminders cron)? Spec defers; first paying customer's feedback drives this.
