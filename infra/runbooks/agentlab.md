# Agentlab — environment runbook

## What it is

A Fly.io app + Postgres pair holding a daily masked refresh of the
production tenant data. Agents use it for bug repro; reviewers use it
for spec validation; preview environments (Phase 8 Implementation
Agent) clone it as their template DB.

Apps:
- `odoo-saas-odoo-agentlab` — Odoo worker (config: [`infra/fly/agentlab/fly.toml`](../fly/agentlab/fly.toml))
- `odoo-saas-odoo-agentlab-db` — Fly Postgres (not yet provisioned; see
  "First-time setup")

Workflow: [`.github/workflows/agentlab-daily-restore.yml`](../../.github/workflows/agentlab-daily-restore.yml).
Spec: [`docs/superpowers/specs/2026-05-16-agentlab-environment-design.md`](../../docs/superpowers/specs/2026-05-16-agentlab-environment-design.md).

---

## What's shipped vs. deferred

### Shipped in this PR

- Fly app config for `odoo-saas-odoo-agentlab`.
- `.github/workflows/agentlab-daily-restore.yml` — daily 02:00 UTC
  cron that wakes the app, pg_dumps staging tenants, restores into
  agentlab, runs the masking script, rotates the reviewer OTP, and
  writes an audit event.
- This runbook.

### Shipped (Phase 5b follow-up)

- **Python masking pipeline.** `infra/agentlab/mask_prod_data.py`
  classifies every column (Odoo `ir_model_fields.ttype`, falling back
  to `information_schema`), applies set-based SQL masking per the
  strategies in `masking-rules.yml`, runs the deny-list regexp pass,
  then samples rows and **fails the workflow** if any PII pattern
  survives. The daily-restore workflow no longer runs warn-only — a
  failed audit blocks the agentlab redeploy. Pure helpers are
  unit-tested in `infra/agentlab/tests/test_masking.py`.

### Deferred (Phase 5b follow-ups, separate PRs)

- **Better Stack log drain wiring.** The agentlab app should ship logs
  with `tenant=agentlab` tagging; needs `BETTERSTACK_LOGS_TOKEN`
  (deferral item from the Phases 2–11 analysis).
- **Grafana dashboard.** Per-tenant panels filterable by wave (spec
  §6); needs Grafana Cloud account first.
- **Sample-row PII audit step.** Once masking ships, the workflow
  step that asserts no PII leaks needs the Python deny-list matcher.

---

## First-time setup

> **Status (2026-05-20):** steps 1–3 are DONE — the Postgres cluster,
> the app, the volume, and the app secrets are provisioned in the
> `personal` Fly org, and the app boots clean (`/web/health` 200). The
> restore workflow's proxy connectivity is wired. The ONLY remaining
> prerequisite is step 4's `STAGING_PG_DSN` secret (and, if staging
> Postgres is a Fly app, the `STAGING_PG_FLY_APP` repo variable — see
> "Daily-restore connectivity"). After that, step 5 can run.

### 1. Provision the agentlab Postgres app

Manual one-off via `flyctl` (cannot live in a workflow because it's a
single-shot creation that has prompts). The Fly org is `personal` — all
the other odoo-saas apps live there, there is no separate `goliatt` org.

```bash
flyctl postgres create \
  --name odoo-saas-odoo-agentlab-db \
  --org personal \
  --region iad \
  --vm-size shared-cpu-1x \
  --volume-size 5 \
  --initial-cluster-size 1 \
  --flex \
  --password "$(openssl rand -hex 20)"
# Note the connection string and password printed at the end —
# they are shown ONCE.
```

### 2. Deploy the agentlab Odoo app

```bash
flyctl apps create odoo-saas-odoo-agentlab --org personal
flyctl volumes create agentlab_data --app odoo-saas-odoo-agentlab \
  --region iad --size 5 --yes
flyctl deploy \
  --app odoo-saas-odoo-agentlab \
  --config infra/fly/agentlab/fly.toml \
  --dockerfile Dockerfile \
  --remote-only
```

### 3. Wire secrets

```bash
flyctl secrets set --app odoo-saas-odoo-agentlab \
  ADMIN_PASSWORD="$(openssl rand -base64 24)" \
  PGHOST=odoo-saas-odoo-agentlab-db.internal \
  PGPORT=5432 \
  PGUSER=postgres \
  PGPASSWORD="<from step 1>"
```

### 4. Add the workflow secrets to the repo

```bash
# DONE 2026-05-20 — set to the .flycast form (see connectivity note below).
gh secret set AGENTLAB_DSN -R GoliattCo/odoo-custom \
  --body "postgres://postgres:<pwd>@odoo-saas-odoo-agentlab-db.flycast:5432/postgres"
# STILL NEEDED — the staging pool's Postgres DSN, read access:
gh secret set STAGING_PG_DSN -R GoliattCo/odoo-custom \
  --body "<staging pool DSN with read access>"
# CONTROL_PLANE_PG_DSN and FLY_API_TOKEN already exist.
```

### 5. Trigger the first restore manually

> Prerequisite: the `STAGING_PG_DSN` secret must be set (step 4). The
> proxy connectivity is handled by the workflow itself — see
> "Daily-restore connectivity" below.

```bash
gh workflow run agentlab-daily-restore.yml \
  -R GoliattCo/odoo-custom \
  -f dry_run=true
gh run watch -R GoliattCo/odoo-custom $(gh run list -R GoliattCo/odoo-custom --workflow=agentlab-daily-restore.yml -L 1 --json databaseId --jq '.[0].databaseId')
```

Once dry-run passes, flip to `dry_run=false` for the real restore.

---

## Daily-restore connectivity

`odoo-saas-odoo-agentlab-db` lives on Fly's private 6PN network —
`*.internal` / `*.flycast` hostnames only resolve inside Fly. A
GitHub-hosted runner, where `agentlab-daily-restore.yml` executes, is
outside that network.

**The workflow handles this itself** (resolved 2026-05-20). On every
run it opens a `flyctl proxy` tunnel:

- **agentlab Postgres** → `127.0.0.1:15432`, always. `AGENTLAB_DSN` is
  rewritten to that local address via
  `infra/scripts/dsn_rewrite_host.py`.
- **staging Postgres** → `127.0.0.1:15433`, only when the repo variable
  `STAGING_PG_FLY_APP` is set (= staging Postgres is itself a Fly app).
  If staging Postgres is publicly reachable (Railway / Neon), leave
  `STAGING_PG_FLY_APP` unset and `STAGING_PG_DSN` is used directly.
- **control-plane Postgres** (Neon) → public, never proxied.

`flyctl` is on the runner (`superfly/flyctl-actions/setup-flyctl`) and
`FLY_API_TOKEN` is a repo secret, so no extra setup is needed. The
tunnels are torn down by an `if: always()` cleanup step.

### If staging Postgres is a Fly app

Set the repo variable so the workflow proxies it too:

```bash
gh variable set STAGING_PG_FLY_APP -R GoliattCo/odoo-custom \
  --body "<staging-postgres-fly-app-name>"
```

Then `STAGING_PG_DSN` should carry the *user/password/database* — its
host:port is rewritten to the local tunnel at run time, so the host in
the stored secret is irrelevant (use the `.flycast` form for clarity).

---

## Reviewer access

Reviewers and agents need browser + SSH access:

### Browser

URL: https://odoo-saas-odoo-agentlab.fly.dev/web/login

Credentials:
- Login: `reviewer@agentlab`
- Password: the OTP rotated by yesterday's restore. Retrieve via:
  ```bash
  flyctl secrets list --app odoo-saas-odoo-agentlab | grep AGENTLAB_REVIEWER_OTP
  ```
  (Secrets are write-only on Fly — actual value is only visible at
  the time of `secrets set`. The restore workflow logs the value as
  an `::notice::` you can retrieve from the GHA run log.)

### SSH

```bash
flyctl ssh console --app odoo-saas-odoo-agentlab
```

Agents authenticate via the same `FLY_API_TOKEN` they use everywhere
else; no separate credential.

---

## Daily operation

The cron runs at 02:00 UTC (= 21:00 Bogotá), wakes the machines via
`fly machines start`, restores fresh data, applies masking, rotates
the OTP, writes an audit event. Workflow timeout is 60 min; current
data volume completes in ~25 min.

To watch the live restore:

```bash
gh run watch -R GoliattCo/odoo-custom \
  $(gh run list -R GoliattCo/odoo-custom \
       --workflow=agentlab-daily-restore.yml -L 1 \
       --json databaseId --jq '.[0].databaseId')
```

To skip a day (e.g. ongoing incident on staging):

```bash
gh workflow disable agentlab-daily-restore.yml -R GoliattCo/odoo-custom
# ...
gh workflow enable agentlab-daily-restore.yml -R GoliattCo/odoo-custom
```

---

## Failure modes

| Symptom | Likely cause | First debug step |
|---|---|---|
| `pg_dump: error: connection to server failed` | `STAGING_PG_DSN` rotated; secret stale | Re-mint staging read-only credentials, `gh secret set` |
| `pg_restore: error: could not connect to database` | Agentlab Postgres app stopped / OOM | `flyctl status --app odoo-saas-odoo-agentlab-db` |
| masking script aborts mid-run | Implementation still skeleton; expected (warn-only) | Track in follow-up issue |
| `audit-event INSERT` fails | `saas_audit` schema not yet applied to control-plane | Apply [`infra/sql/saas-audit-event-schema.sql`](../sql/saas-audit-event-schema.sql) |
| OTP rotation fails after deploy | Fly machines didn't restart cleanly | `flyctl machines list --app odoo-saas-odoo-agentlab` + manual restart |
| Workflow times out (>60min) | Tenant volume exceeded sizing | Bump `timeout-minutes` in workflow OR split per-tenant matrix |

---

## Network policy

Agentlab is sensitive (it holds tenant data, even masked). Egress is
restricted to:

- `github.com` (pull addon code if needed)
- `api.anthropic.com` (LLM calls from agents running against agentlab)
- `*.fly.dev` (Fly internal routing)
- the staging Postgres endpoint (for the daily restore)

Configure via the Fly outbound firewall once Fly exposes it for
non-enterprise plans; until then, document the expected allow-list
in code review (see [`infra/fly/agentlab/fly.toml`](../fly/agentlab/fly.toml)
header for the explicit list).

---

## Related work

- Spec: [`docs/superpowers/specs/2026-05-16-agentlab-environment-design.md`](../../docs/superpowers/specs/2026-05-16-agentlab-environment-design.md)
- Masking allow-list: [`infra/agentlab/mask-allowlist.yml`](../agentlab/mask-allowlist.yml)
- Masking rules: [`infra/agentlab/masking-rules.yml`](../agentlab/masking-rules.yml)
- Audit table: [`saas_audit.event`](./saas-audit-event.md)
- Phase 8 dependency: Implementation Agent preview envs spawn from agentlab DB as a template.
