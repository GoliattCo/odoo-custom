# Staging per-tenant rollback drill

How to prove the per-tenant rollback paths end-to-end against a
non-production Postgres before exercising them in prod under load.

Two paths to drill — they coexist in `rollback.run()`:

1. **`pg_dump` / `pg_restore` (Option B — primary path)** — per-tenant,
   selective. Implementation:
   `docs/superpowers/specs/2026-05-27-per-tenant-restore-design.md`.
2. **`pgbackrest` cluster restore** (legacy / DR floor) — cluster-wide,
   stops Postgres + WAL replay. Drill against staging required before
   ever firing in prod with `PGBACKREST_DRY_RUN=false`.

Pairs with Tier 5 Items 1 and 2 of
[`docs/superpowers/specs/2026-05-16-promote-to-prod-design.md`](../../docs/superpowers/specs/2026-05-16-promote-to-prod-design.md).
**Operator-owned drill** — does not run on a schedule.

## Prereqs (operator fills these in before running)

| Item | Recommended value | This drill's value |
|---|---|---|
| Staging Postgres Fly app name | `odoo-saas-postgres-staging` | _TBD_ |
| pgbackrest S3 prefix | `staging/` subpath of `goliatt-odoo-saas-hot`, OR separate bucket | _TBD_ |
| pgdump S3 prefix | `staging-pgdump/` subpath of the same bucket | _TBD_ |
| Synthetic tenant slug | `acmesas-test`, `acmesas-test2` | _TBD_ |
| `FLY_SSH_TOKEN_POSTGRES_STAGING` | New Fly token, ssh-scoped on the staging app | _TBD_ |

## Phase 1 — Stand up the staging Postgres

```bash
APP=odoo-saas-postgres-staging   # ← operator choice
S3_BUCKET="${PGBACKREST_REPO1_S3_BUCKET}"  # reuse prod bucket
S3_PREFIX=staging                # ← isolate from prod stanza

flyctl apps create "$APP"

# Mirror the prod fly.toml, override app + S3 prefix
cp infra/fly/postgres/fly.toml /tmp/staging-fly.toml
sed -i '' "s/^app *= *\"odoo-saas-postgres\"/app = \"$APP\"/" /tmp/staging-fly.toml

# Same secrets as prod EXCEPT a distinct PGBACKREST_REPO1_PATH
flyctl secrets set --app "$APP" \
  POSTGRES_PASSWORD="<from prod secret manager>" \
  PGBACKREST_REPO1_S3_BUCKET="$S3_BUCKET" \
  PGBACKREST_REPO1_S3_REGION="<prod-region>" \
  PGBACKREST_REPO1_S3_KEY="<prod-iam-key>" \
  PGBACKREST_REPO1_S3_KEY_SECRET="<prod-iam-secret>" \
  PGBACKREST_REPO1_CIPHER_PASS="<distinct-cipher-pass>" \
  PGBACKREST_REPO1_PATH="/$S3_PREFIX/shared"

flyctl volumes create pgdata --app "$APP" --size 10 --region iad

# IMPORTANT: deploy uses the postgres image that ships pgdump-snapshot.sh
# and pgrestore-snapshot.sh — must be built from main (post PR #121 merge).
flyctl deploy --app "$APP" --config /tmp/staging-fly.toml \
  --dockerfile infra/postgres/Dockerfile --remote-only
```

## Phase 2 — Seed two synthetic tenants

Two tenants is what proves the *selective* per-tenant property — we
roll back one and verify the other is intact.

```bash
SLUG_A=acmesas-test
SLUG_B=acmesas-test2

# Provision through the SaaS gateway against the staging Odoo
PROVISIONING_URL="https://<staging-odoo>/saas/provision" \
PROVISIONING_SECRET="<hmac-secret>" \
  ./scripts/provision-tenant.sh "$SLUG_A"

PROVISIONING_URL="https://<staging-odoo>/saas/provision" \
PROVISIONING_SECRET="<hmac-secret>" \
  ./scripts/provision-tenant.sh "$SLUG_B"

# Insert distinguishable canary rows in BOTH tenants
for SLUG in "$SLUG_A" "$SLUG_B"; do
  flyctl ssh console --app "$APP" -C "sh -c '
    gosu postgres psql -d $SLUG -c \"
      CREATE TABLE IF NOT EXISTS rollback_canary (
        id serial PRIMARY KEY,
        marker text NOT NULL,
        created timestamptz default now()
      );
      INSERT INTO rollback_canary (marker) VALUES (\\\"pre-snapshot-$SLUG\\\");
    \"
  '"
done
```

## Phase 3 — Drill A: `pg_dump`/`pg_restore` per-tenant (Option B)

This is the primary path going forward. Proves the selective
property.

```bash
# Take a pgdump snapshot of tenant A
flyctl ssh console --app "$APP" -C "sh -c '
  /usr/local/bin/pgdump-snapshot.sh $SLUG_A $SLUG_A
'" 2>&1 | tee /tmp/snap-a.log

# Pull the SNAPSHOT_KEY out of the wrapper's last line
KEY_A=$(grep '^SNAPSHOT_KEY=' /tmp/snap-a.log | tail -1 | cut -d= -f2)
echo "Tenant A snapshot: $KEY_A"

# Insert a destructive change AFTER the snapshot (tenant A only)
flyctl ssh console --app "$APP" -C "sh -c '
  gosu postgres psql -d $SLUG_A -c \"
    INSERT INTO rollback_canary (marker) VALUES (\\\"post-snapshot-WILL-BE-GONE\\\");
  \"
'"

# Insert a NON-destructive change in tenant B (must survive)
flyctl ssh console --app "$APP" -C "sh -c '
  gosu postgres psql -d $SLUG_B -c \"
    INSERT INTO rollback_canary (marker) VALUES (\\\"post-snapshot-MUST-SURVIVE\\\");
  \"
'"

# Roll back tenant A ONLY via the staging migration-runner
# (assumes the runner is pointed at the staging postgres via
#  PGBACKREST_SSH_APP=$APP and SNAPSHOT_MODE=pgdump)
JOB_ID=<uuid of a tenant_migration_jobs row whose snapshot_id=$KEY_A>
PREV_SHA=<rollback target sha>
flyctl ssh console --app odoo-saas-migration-runner -C "sh -c '
  ROLLBACK_ACTOR=staging-drill python -m migration_runner.rollback $JOB_ID $PREV_SHA
'" 2>&1 | tee /tmp/rollback.log

# Expected log lines:
# - rollback start job=... snapshot=pgdump/$SLUG_A/<ts>.dump dry_run=False
# - rollback complete (pgdump) job=... dry_run=False
# - rollback OK job=...

# Verify tenant A's marker is GONE
flyctl ssh console --app "$APP" -C "sh -c '
  gosu postgres psql -d $SLUG_A -c \"SELECT marker FROM rollback_canary;\"
'"
# Expected: only `pre-snapshot-$SLUG_A`. NO `post-snapshot-WILL-BE-GONE`.

# Verify tenant B's marker SURVIVES (selective rollback property)
flyctl ssh console --app "$APP" -C "sh -c '
  gosu postgres psql -d $SLUG_B -c \"SELECT marker FROM rollback_canary;\"
'"
# Expected: BOTH `pre-snapshot-$SLUG_B` AND `post-snapshot-MUST-SURVIVE`.
```

**Acceptance (Item 2 + Item 1 combined for the pgdump path):**

- ✓ `pg_restore` exits 0; rollback CLI exits 0.
- ✓ Tenant A's `post-snapshot-WILL-BE-GONE` row is gone.
- ✓ Tenant B's `post-snapshot-MUST-SURVIVE` row is intact.
- ✓ Control-plane `tenants.last_migrated_sha` for A reverted; B unchanged.

## Phase 4 — Drill B: cluster-wide `pgbackrest` restore (DR floor)

The legacy cluster-restore path still ships — `rollback.py` takes it
when `snapshot_id` is a pgbackrest label (no `pgdump/` prefix). Drill
against staging before ever flipping `PGBACKREST_DRY_RUN=false` in
prod.

**Catastrophic-if-fired-in-prod:** pgbackrest restore stops Postgres
and replays WAL into the data dir → wipes every tenant on the
cluster. The staging Postgres has only synthetic tenants so the
blast radius is contained.

```bash
# Take a pgbackrest cluster backup
flyctl ssh console --app "$APP" -C "sh -c '
  gosu postgres pgbackrest --stanza=shared --type=full backup
'"

# Insert a marker in both tenants after the backup
for SLUG in "$SLUG_A" "$SLUG_B"; do
  flyctl ssh console --app "$APP" -C "sh -c '
    gosu postgres psql -d $SLUG -c \"
      INSERT INTO rollback_canary (marker) VALUES (\\\"after-pgbackrest-WILL-VANISH\\\");
    \"
  '"
done

# Capture the most recent backup label
LABEL=$(flyctl ssh console --app "$APP" -C "sh -c '
  gosu postgres pgbackrest --stanza=shared info --output=json
'" | jq -r '.[0].backup[-1].label')
echo "Restoring to label: $LABEL"

# Stage the migration-runner to target staging with DRY_RUN=false
flyctl secrets set --app odoo-saas-migration-runner \
  PGBACKREST_SSH_APP="$APP" \
  PGBACKREST_DRY_RUN=false

# Fire rollback via the daemon's CLI — uses a hand-built row whose
# snapshot_id is the pgbackrest LABEL (not a pgdump key)
flyctl ssh console --app odoo-saas-migration-runner -C "sh -c '
  ROLLBACK_ACTOR=staging-drill python -m migration_runner.rollback <JOB_ID> <PREV_SHA>
'"

# Verify BOTH tenants reverted (cluster-wide property)
for SLUG in "$SLUG_A" "$SLUG_B"; do
  flyctl ssh console --app "$APP" -C "sh -c '
    gosu postgres psql -d $SLUG -c \"SELECT marker FROM rollback_canary;\"
  '"
done
# Expected for EACH tenant: NO `after-pgbackrest-WILL-VANISH` row.
# This confirms the cluster-wide blast radius — and that the path
# works at all.
```

**Acceptance (Item 1 acceptance for pgbackrest path):**
- ✓ `pgbackrest info` returns the staged tag.
- ✓ `pgbackrest --set=<tag> --delta restore` exits 0.
- ✓ Control-plane `tenants.last_migrated_sha` reverted.
- ✓ Both tenants lost their post-backup canary rows (proves restore
  actually moved data — not a quiet no-op).

## Phase 5 — Restore the migration-runner to prod safety

**Required** after Phase 4. Leaving the staging target wired makes
the next prod rollback go to the wrong cluster.

```bash
flyctl secrets set --app odoo-saas-migration-runner \
  PGBACKREST_SSH_APP=odoo-saas-postgres \
  PGBACKREST_DRY_RUN=true
flyctl secrets set --app odoo-saas-migration-runner \
  FLY_API_TOKEN="<prod-postgres-ssh-token>"  # FLY_SSH_TOKEN_POSTGRES

# Sanity check
flyctl ssh console --app odoo-saas-migration-runner -C 'env' \
  | grep -E "PGBACKREST_(SSH_APP|DRY_RUN)|SNAPSHOT_MODE"
# Expected: PGBACKREST_SSH_APP=odoo-saas-postgres
#           PGBACKREST_DRY_RUN=true
#           SNAPSHOT_MODE=pgdump  (or ssh, depending on rollout phase)
```

## Phase 6 — Tear down (optional)

If the staging cluster was only stood up for this drill:

```bash
flyctl apps destroy "$APP" --yes
# Don't auto-delete the S3 backups — keep them for forensic review.
# Manual cleanup later: aws s3 rm s3://<bucket>/staging/ --recursive
#                      aws s3 rm s3://<bucket>/staging-pgdump/ --recursive
```

## What the combined drill proves

**Phase 3 (pgdump) proves:**
- `pgdump-snapshot.sh` actually writes a usable dump to S3.
- `pgrestore-snapshot.sh` actually replays it correctly.
- `_rollback_via_pgrestore`'s argv shape works against a live machine.
- **Selectivity** — pg_restore on tenant A does NOT touch tenant B.
- Control-plane audit row + sha revert happen atomically.

**Phase 4 (pgbackrest) proves:**
- The existing `_pgbackrest_argv --set <label> --delta restore` path
  works against a live cluster (not just `info`).
- Tier 5 Item 1 acceptance for the legacy path.

## Reference good outcomes

- Drill ID: _TBD — fill in after first successful run_
- Phase 3 snapshot key: _TBD_
- Phase 4 pgbackrest label: _TBD_
- Wall-clock per phase: _TBD_
