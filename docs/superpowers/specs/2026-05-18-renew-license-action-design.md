# Renew License Action — Design Spec

**Date:** 2026-05-18
**Author:** Manuel Caro (with Claude)
**Status:** Draft
**Spec type:** design spec
**Scope of work:** Atomic revoke-old + issue-new mutation for renewing an enterprise license. v1 of the operator UI made the operator click both buttons; this adds a single "Renew" action that does both in one transaction with rollback if either side fails.

---

## 1. Goal

When an enterprise customer renews their license, the operator currently has to (a) revoke the old license, (b) mint a new one with the same customer_ref + same image_sha256 + a fresh term. Two clicks, two audit_log rows, two opportunities to leave the customer in an inconsistent state if step (b) fails after step (a) succeeded.

Replace with a single `Renew` button on the license detail page that runs both in a Drizzle transaction. Either both happen or neither does. Audit gets a single `license.renew` row tying the two together via correlation.

## 2. Non-goals

- Not changing the renewal terms model. New license gets the same `image_sha256`, `allowed_modules`, and `customer_ref`; only `expires_at` + `grace_until` shift forward (default 365 + 14 days from now).
- No customer-facing renewal flow (customer can't self-serve renewals; that's intentional — operator confirms payment first).
- Not deleting the old license. Revoke keeps the row (for audit history); only `revoked_at` + `revoked_reason` get set.
- Not modifying the license-expiry-reminder cron — it stops firing once the OLD license is revoked (its WHERE clause skips revoked rows).

## 3. Tenancy impact

None. Control-plane operation on operator-internal table. No tenant boundary touched.

## 4. Data model changes

None. Uses the existing `enterprise_licenses` table:
- UPDATE old row: `revoked_at = NOW()`, `revoked_reason = 'renewed: superseded by ' || new_id`
- INSERT new row: copies customer_ref + image_sha256 + allowed_modules + notes from old; new id; new expires_at + grace_until per term/grace inputs

Audit_log gets ONE row (`action='license.renew'`) with `payload = {old_license_id, new_license_id, term_days, grace_days, reason}`.

## 5. API surface

**New tRPC mutation `enterpriseLicenses.renew`:**

```ts
renew({
  oldLicenseId: string (uuid),
  termDays?: number (default 365, min 1, max 3650),
  graceDays?: number (default 14, min 0, max 365),
  reason?: string (max 500) // operator-facing note
})
```

Returns `{ oldLicenseId, newLicenseId, newExpiresAt, newGraceUntil }`.

Implementation in a single `db.transaction(async tx => { ... })`:
1. SELECT the old license; throw NOT_FOUND if missing, CONFLICT if already revoked.
2. UPDATE old row to set revoked_at + revoked_reason.
3. INSERT new row with copied immutable fields + fresh dates.
4. INSERT audit_log row tying both ids.
5. Return ids + dates.

**New server action `renewLicenseAction`** in `apps/admin/app/lib/actions/licenses.ts`. Same `{ok, data} | {ok, error}` contract as the existing mint/revoke/restore.

**UI:** detail page action bar gets a `Renew…` button next to Revoke (when license is not yet revoked). Opens a `RenewDialog` with optional inputs for termDays/graceDays/reason; defaults pre-filled. Confirms → server action → toast → redirects to NEW license's detail page.

## 6. Security model

Operator-only (same `operatorProcedure` gate as existing mutations). Defense-in-depth `requireOperator()` inside the server action.

No new authorization risk; this is just a transactional combination of two existing operations both of which already require operator role.

## 7. Test plan

**Unit (vitest):**
- `renew()` happy path: old license revoked, new license created with the same image_sha256, audit row written, return shape correct.
- Renewing an already-revoked license throws CONFLICT, transaction rolls back, neither row mutated.
- Renewing a non-existent license throws NOT_FOUND.
- Mocked DB failure during the INSERT (between UPDATE and audit_log): assert the transaction aborts — old license stays unrevoked.
- Server action: VALIDATION on bad termDays / graceDays / non-uuid oldLicenseId.

**Integration (ephemeral Neon):**
- Real DB round-trip: renew, verify both rows exist in expected states, verify audit_log row is correct.
- Concurrent renewal of the same old license: only one succeeds; the second gets CONFLICT.

**E2E (Playwright):**
- Mint a license → click Renew → fill defaults → confirm → land on new license detail. Old license accessible via direct URL shows `revoked` status with reason "renewed: superseded by …".

## 8. Rollout plan

Single PR. Additive (new procedure, new action, new dialog). No schema migration.

**Wave:** canary. Operator can keep using the manual two-step until they trust the new button.

**Rollback:** revert the PR. Manual two-step still works.

## 9. Observability

- Server action logs `{action: 'renewLicense', actor, oldLicenseId, newLicenseId, ok, duration_ms}`.
- audit_log row is canonical record.
- No new alerts.

## 10. Open questions

1. **Should the new license inherit `notes` from the old one?** Pro: continuity. Con: stale notes (e.g. "non-payment 90 days past due" copies onto the renewal). Recommendation: do NOT copy notes; renewed license gets fresh empty notes; operator adds new notes if relevant.
2. **Should `allowed_modules` change at renewal?** Today the field is set at mint time and immutable. Renewal could re-enter it; spec defaults to copying old → new (simpler, no surprises). If a customer signed up for more/fewer modules at renewal, operator can revoke + mint manually (escape hatch).
3. **Notification to customer of the new LICENSE_ID:** does the renewal action automatically send the customer an email with the new id? Or operator does it manually? v1 = manual (matches today's pattern). v2 nice-to-have = optional email checkbox on the Renew dialog that fires Resend with the new id.
4. **Renewing a license with a still-valid future expires_at:** allowed? E.g., customer pre-pays 2 years; renew on month 11 means the new license starts now (overlapping the old). Some payment systems expect this (don't carry remaining days forward). Recommendation: allow (operator decides); document the overlap behavior in the UI's dialog description.
