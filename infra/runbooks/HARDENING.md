# Phase 2 Hardening Runbook

State the **specific control**, **why** it's not in Phase 1, and the **exact
steps** to land it. Everything below is intentionally deferred from Phase 1 in
favor of getting the system observably operational first.

## 1. `/web/database/*` access control

**State today:** Odoo's master-password endpoints (`/web/database/create`,
`/manager`, `/restore`, `/backup`, `/drop`) are reachable on:
- `https://<slug>.app.goliatt.co/*` (Railway edge → Odoo, no IP gate)
- `https://<slug>.fly.app.goliatt.co/*` (Fly Traefik → Odoo; `dynamic.yml`'s
  `saas-database-allowlist` middleware only contains `127.0.0.1/32` today)

The only protection is the strong random `ADMIN_PASSWORD` set on each Odoo
deployment. That's authentication; no authorization layer beyond it.

**Risk:** anyone who learns the master password gets full DB-management. The
provisioning workflow needs to call this endpoint, so we can't simply block
it everywhere.

**Phase 2 fix — pick ONE:**
- **A. Cloudflare Worker proxy** on a sibling subdomain (e.g.,
  `db.app.goliatt.co`) that requires a shared-secret header. The Vercel
  control plane calls `https://db.app.goliatt.co/dispatch?slug=<x>` with the
  secret; the worker re-emits the request to `<x>.app.goliatt.co/web/database/*`.
  Then a CF firewall rule blocks public `/web/database/*` everywhere.
- **B. Vercel Secure Compute (static egress IPs)** + Traefik IP allowlist.
  Pro/Enterprise feature on Vercel; gives stable egress IPs to allowlist.
  Cleanest if you already pay for it.
- **C. mTLS or signed-URL pattern** — the control plane signs the request
  with a key only it has; Odoo verifies via a small middleware addon. Most
  invasive but no infra deps.

Recommendation: **A** for cost, **B** for simplicity if you're already on
Vercel Pro.

## 2. Log drains + observability

**State today:** stdout/stderr in each platform's native log viewer
(Railway dashboard, `flyctl logs`, Vercel function logs). No retention
guarantee, no aggregated search, no metrics.

**Phase 2 fix:**
- Sign up for an observability vendor (Axiom, Better Stack / Logtail, Datadog).
- **Vercel:** Settings → Logs → "Connect a Log Drain". Pick the vendor; Vercel
  ships function logs in near real time.
- **Railway:** Project → Settings → Log Drains (Hobby+). Same idea.
- **Fly:** `flyctl logs` is realtime but doesn't retain. Run a NATS consumer
  (the underlying Fly logs are on NATS); or use the
  `superfly/fly-log-shipper` app and target the same vendor.

Pick fields/levels in the vendor and set alerts on:
- Vercel function errors > N/min
- Odoo `CRITICAL` lines from any platform
- pgBackRest backup-runner non-zero exits
- Cron job failures (Vercel emits `cron.failed`)

## 3. Clerk session-claims migration

**State today:** the admin app gates `isOperator` on
`OPERATOR_USER_IDS` (comma-separated env var, one per intended operator).
This is documented as a Phase 1 shortcut in
`apps/admin/app/api/trpc/[trpc]/route.ts`.

**Phase 2 fix:**
1. In Clerk dashboard → Sessions → Customize session token, add a public
   metadata field `role` to the JWT template:
   ```json
   {
     "publicMetadata": "{{user.public_metadata}}"
   }
   ```
2. For each operator user: dashboard → Users → click user → Public metadata →
   `{"role": "operator"}`.
3. Update the route handler in `apps/admin/app/api/trpc/[trpc]/route.ts`:
   ```ts
   const { sessionClaims } = await auth();
   const isOperator = sessionClaims?.publicMetadata?.role === 'operator';
   ```
4. Delete `OPERATOR_USER_IDS` from Vercel env (no longer read).

Survives operator-team changes without redeploys.

## 4. Restore drill

**State today:** pgBackRest writes WAL + base backups to S3 on both Railway
and Fly. Nobody has actually restored from those backups end-to-end. The
plan calls for quarterly drills.

**Phase 2 fix:**
1. Run on a non-prod schedule (suggest: 1st of each quarter, manual trigger
   via `workflow_dispatch` on a new `.github/workflows/restore-drill.yml`).
2. Pick a random tenant backup from the catalog.
3. `pgbackrest --stanza=shared --pg1-path=/tmp/restore-test restore` into
   an ephemeral container.
4. Diff `pg_dump` of the restored DB against a baseline; fail loud on diff.
5. If a backup is older than 12 months and hasn't been drill-tested,
   mark its `tenant_backups.state` = `untrusted` (plan's commitment).

Skeleton workflow lives at `.github/workflows/restore-drill.yml.todo`
(create when you have a non-prod stanza to restore into).

## 5. Filestore backups (the backup-runner re-design)

**State today:** the backup-runner service was scaffolded but skipped on
Railway because Railway volumes are single-service (the runner can't mount
Odoo's filestore volume). Phase 1 falls back to pgBackRest base backups
only — covers the Postgres half but **not** the filestore half (attachments,
generated PDFs, large fields).

**Phase 2 fix — pick ONE:**
- **A. Co-locate the runner inside the Odoo container** as a sidecar
  process started by the entrypoint (busybox crond + a backup script). It
  has direct access to `/var/lib/odoo/filestore`. Simple; couples backup
  cadence to Odoo image deploys.
- **B. Cron Postgres-side rsync** — mount the filestore on the Postgres
  service via a shared volume (Railway: not supported; Fly: requires the
  filestore live on Postgres' VM, not Odoo's — re-architecture).
- **C. Odoo-internal scheduled action** that streams the filestore to S3
  using the control plane's KMS-wrapped DEK. No sidecar, no second container,
  but lives inside Odoo's runtime (must use Odoo's cron + custom addon).

Recommendation: **C** — keeps the data-plane/control-plane separation
clean and gives per-tenant scheduling for free via Odoo's cron.

## 6. Operator Odoo isolation

**State today:** the operator Odoo runs as a tenant DB (`operator`) in the
SAME Odoo HTTP server that serves customer tenants on Railway. Not
isolated.

**Phase 2 fix:** deploy a dedicated `odoo-saas-operator` Fly/Railway app
running the same image but in single-DB mode (extend the entrypoint with
a `SINGLE_DB=<name>` mode that bypasses dbfilter). Move the operator DB
there; customer tenants stay on the shared pool. Customer-side incidents
no longer touch the operator's books.

## 7. Tenant subdomain regex enforcement at the edge

The control-plane regex (`^[a-z0-9][a-z0-9-]{1,38}[a-z0-9]$`) is enforced
when creating tenants, but the data-plane edges (Railway, Traefik) accept
anything matching `*.app.goliatt.co`. A request to a non-existent
`<random>.app.goliatt.co` hits Odoo → dbfilter resolves to a DB that
doesn't exist → Odoo logs the failure. Cheap but noisy.

**Phase 2 fix:** Traefik can enforce the regex on its router rule (the
`saas-tenants-wildcard` router in `dynamic.yml` already uses
`HostRegexp` with that exact pattern). Railway's edge has no such filter;
add a Cloudflare Worker that rejects non-conforming hostnames before they
hit the Railway edge.
