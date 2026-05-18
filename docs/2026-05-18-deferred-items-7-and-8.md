# Deferred items 7 & 8 — why no code action today

These are tracked in [project_hardening_progress.md] and elsewhere as
genuinely blocked rather than just unprioritized. Documenting WHY so a
future operator (or me on a future session) doesn't accidentally try to
implement them and discover the blockers from scratch.

---

## Item 7 — HARDENING item 7 Railway-half edge filter

**Goal:** tighten the `*.app.goliatt.co` Railway-edge router rule so
unknown subdomains 404 at the edge instead of reaching the Odoo
container.

**Status:** Fly half shipped 2026-05-15 (data-plane commit `d0fa18c`,
Traefik `HostRegexp` tightened to match the control-plane validator).
Railway half **deliberately deferred**.

**Why blocked:** Putting a Cloudflare Worker or WAF Custom Rule in
front of `*.app.goliatt.co` requires CF to terminate TLS for the
wildcard. Cloudflare Universal SSL on the free plan covers
`*.goliatt.co` (one level) but NOT two-level wildcards like
`*.app.goliatt.co`.

The only paid options that cover it:

| Option | Cost | Verdict |
|---|---|---|
| Advanced Certificate Manager | $10/mo or $99/yr | Not worth the spend |
| Cloudflare for SaaS | metered per-cert | Heavier integration |
| Migrate to paid CF plan | $20-$200/mo | Out of scope |

**Operator decision (2026-05-15):** $99/yr isn't worth it because the
`saas_provisioning_gateway` lockdown.py addon already 404s on unknown
DBs at the app level — the marginal hardening is defense-in-depth only,
not a real security gap.

**When to reopen:**
- We move to a paid CF plan for other reasons (then this comes free)
- We observe actual abusive traffic patterns at Railway's edge that the
  app-level 404 isn't catching fast enough
- Memory: [reference-cf-two-level-wildcard-tls]

**Effort if/when unblocked:** ~half a day. Write a Worker that
short-circuits requests whose Host doesn't match the
saas-tenant-slug regex, deploy via `wrangler`. The Fly half is the
reference pattern.

---

## Item 8 — Cross-platform moveTier unregister-route

**Goal:** when `moveTier` migrates a tenant from Fly → Railway (or
vice versa), the SOURCE platform's Traefik router for that tenant must
be removed at the same time the TARGET platform's router goes up.

**Status:** Same-platform `Fly → Fly` works (drill #17 was zero-touch,
53 s wall-clock). The cross-platform branch in `moveTier`'s
`dropSourceAndFinalize` step is **wired** (data-plane `d8ec44d` added
`unregister-route` to `/v1/admin-ops`) but **never executes** end-to-end
because the path is gated on a SOURCE-side backup-runner that doesn't
exist on Railway today.

**Why blocked:** The backup-runner service was originally designed to
exist on both platforms (per Phase 1 design). It currently exists ONLY
on Fly (`odoo-saas-backup-runner.fly.dev`). The Railway equivalent
service has never been spun up because:
- Railway services share a single Volume per service, so a backup
  runner sidecar would need its own Volume separate from the Odoo data
  Volume (Phase 1 design choice).
- No Railway tenant has hit the migration scenario that exercises this
  path yet — `acmesas2` (the only shared-tier active tenant) lives on
  Fly.

**When to reopen:**
- A tenant on Railway needs to migrate to Fly or to per-tenant
  exclusive infra
- Or: we decide to consolidate the backup-runner deployment to a
  single platform (likely Fly, since it's already there) and have
  Railway-side calls hit `odoo-saas-backup-runner.fly.dev` over the
  internet. Trade-off: slight latency for backup operations, but
  removes the second deployment surface.

**Effort if/when unblocked:**
- Option A (deploy Railway runner): ~1 day. The `infra/backup-runner/`
  source is platform-agnostic; needs a Railway service definition +
  Volume mount + secrets. The data-plane already has the Railway
  scaffolding for adjacent services (pgbouncer landed 2026-05-15 the
  same way).
- Option B (cross-platform runner calls): ~half a day. Update moveTier
  to call the Fly runner regardless of the SOURCE platform, with
  appropriate Host header + auth.

Memory: [project-hardening-progress] section "Item 7" + Phase 3 drill
notes in [project-saas-plan].

---

## What I'm NOT deferring

These were considered for blocker-status but are genuinely doable; they
landed this session:

- ✅ Item 5 (enforcement decorators on saas_license_gate) — was "wait
  for live customer pressure"; we no longer need to wait because the
  code is robust enough to land safely with `verdict=='active'` being
  the default-on case.
- ✅ Item 6 (streaming AEAD) — was "wait for a tenant to hit 256 MiB";
  we no longer need to wait because the v1 path stays the default for
  small files and v2 is auto-dispatched only when needed.

Pattern worth noting: "wait for X to happen first" is sometimes
legitimate scope-control, but sometimes a self-fulfilling defer. For
items 5+6 today, the work fit in single-commit-sized changes with
backward-compat dispatch — no need to wait. For items 7+8 above, the
work is gated on external decisions ($$$ for 7, infrastructure
choice for 8) that haven't been made.
