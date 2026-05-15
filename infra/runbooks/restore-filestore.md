# Filestore restore runbook

How to recover a tenant's `/var/lib/odoo/filestore/<db>` from the WARM S3
tier when the live filestore is lost, corrupted, or needs to roll back to
a known-good point.

Pairs with the database restore (logical_dump or pgBackRest cluster
restore — separate runbook in `HARDENING.md`). Filestore + database must
move to the same point in time, otherwise `ir.attachment` rows reference
filestore objects that don't exist (or vice versa) and the UI breaks
visibly.

## Prereqs

- Operator workstation with:
  - Repo clone at `~/Odoo-control-plane`
  - Node 22 + pnpm 9
  - AWS creds for the backup-runner IAM role (S3 + KMS on the warm bucket)
  - `DATABASE_URL` for the control plane Neon instance (the same one the
    Vercel admin app talks to)
- `flyctl` or `railway` CLI for whichever platform hosts the target tenant

## Steps

### 1. Identify the target

```bash
psql "$DATABASE_URL" -c "
  SELECT id, slug, db_name, state
    FROM tenants WHERE slug='<tenant-slug>';"
```

You need `db_name` (matches the tenant's Postgres database name AND the
top-level directory inside the tar — see addon `_tar_filestore` adding
`arcname=db_name`).

### 2. Pick a backup row

```bash
psql "$DATABASE_URL" -c "
  SELECT id, completed_at, size_bytes, sha256
    FROM tenant_backups
   WHERE tenant_id = (SELECT id FROM tenants WHERE slug='<tenant-slug>')
     AND backup_type = 'filestore_tar'
     AND state = 'completed'
   ORDER BY completed_at DESC
   LIMIT 10;"
```

Default for the CLI is the latest completed row; pin to a specific id
with `--backup=<uuid>` if you're rolling back to a known-good point.

### 3. Decrypt to local disk

```bash
cd ~/Odoo-control-plane
set -a; . apps/admin/.env.local; set +a
export AWS_ACCESS_KEY_ID=...        # NOT in .env.local — pulled from ops vault
export AWS_SECRET_ACCESS_KEY=...

pnpm --filter @odoo-saas/backup restore -- \
  --tenant=<tenant-slug> \
  --backup=<uuid|omit-for-latest> \
  --out=/tmp/<tenant-slug>.tar \
  --extract=/tmp/<tenant-slug>-fs
```

The CLI verifies the SHA-256 against the catalog row, KMS-unwraps the
per-tenant DEK, AES-256-GCM decrypts atomically, then optionally
`tar -xf`s into `/tmp/<tenant-slug>-fs`. The extracted root is the
tenant's `db_name`.

A `ciphertext sha256 mismatch` (exit 4) means the S3 object is corrupt
or the catalog row is wrong — file a P1, do NOT proceed.

### 4. Stage the target

Stop the Odoo worker pods on the tenant's platform so no in-flight write
re-creates entries in the filestore mid-restore:

**Railway** (tenant pool, e.g. `acmesas2`):
```bash
railway down --service odoo
# scale back to 1 after the swap
```

**Fly** (tenant pool):
```bash
flyctl machine stop --app odoo-saas-odoo <machine-id>
```

### 5. Swap the filestore tree

Both platforms mount the filestore on a persistent volume at
`/var/lib/odoo/filestore`. SSH or `flyctl ssh console` into a worker
machine, then:

```bash
mv /var/lib/odoo/filestore/<db_name> /var/lib/odoo/filestore/<db_name>.old.$(date +%s)

# Transfer the extracted tree (the CLI extracted /tmp/<tenant-slug>-fs
# locally; rsync or scp to /tmp on the platform host first, or use
# flyctl sftp/railway scp).
# Then:
mv /tmp/<tenant-slug>-fs/<db_name> /var/lib/odoo/filestore/<db_name>
chown -R odoo:odoo /var/lib/odoo/filestore/<db_name>
```

If you also restored the DB (logical_dump or pgBackRest), do the DB swap
first — Odoo will rebuild attachment caches on next access only if the
DB rows are present.

### 6. Restart workers + smoke-test

```bash
# Railway
railway up --service odoo
# Fly
flyctl machine start --app odoo-saas-odoo <machine-id>

# Smoke:
curl -I https://<tenant>.app.goliatt.co/web/login   # expect HTTP 200
# Log in and open a record with a known attachment — confirm preview
# / download works (catches filestore↔db row mismatches).
```

### 7. Stamp the catalog row

```bash
psql "$DATABASE_URL" -c "
  UPDATE tenant_backups
     SET restore_tested_at = NOW()
   WHERE id = '<backup-uuid>';"
```

This is what the 12-month-untrusted sweep keys on — verified backups stop
the "no recent restore" alert from firing.

### Common failure modes

| Symptom | Cause | Fix |
|---|---|---|
| `ciphertext sha256 mismatch` (exit 4) | S3 object corrupted between upload and now (bitrot) OR catalog row tampered | Pick a different backup; raise P1 if multiple rows mismatch |
| `Unsupported state or unable to authenticate data` (exit 5) | GCM tag invalid — wrong DEK, wrong nonce, or wrong tag stored | Verify catalog row's `encryption_key_id` and `tenant_dek.kms_cmk_arn` agree; check `storage_url` fragment hex lengths |
| `Could not load credentials from any providers` | Missing AWS creds in shell | `export AWS_ACCESS_KEY_ID=...; export AWS_SECRET_ACCESS_KEY=...` |
| Attachments 404 after restart | Filestore restored, DB row still references an older filestore path | Restore the matching-day logical_dump (or pgBackRest snapshot) and re-swap |
