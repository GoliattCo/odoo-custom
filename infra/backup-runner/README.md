# Backup runner

Small HTTP service that performs tenant backup operations close to the data:

1. `pg_dump -Fc -j 4` against the tenant DB.
2. `tar -cf` of the tenant's filestore directory.
3. AES-256-GCM encryption of the combined artifact (header + dump + filestore + auth tag).
4. Multipart upload to the WARM S3 bucket.
5. Returns the storage URL, sha256, size, LSN, nonce, and auth tag.

Lives in the data plane (alongside Postgres on Railway / Fly) rather than the
Vercel control plane because it shells out to `pg_dump` and reads gigabytes
from local volumes — neither of which Vercel Functions are a good fit for.

## API

All requests authenticated by `Authorization: Bearer ${BACKUP_RUNNER_TOKEN}`.
Reject without the token; never echo the token in errors.

| Endpoint | Body | Result |
|---|---|---|
| `GET /health` | none | `{ ok: true }` for platform liveness probes. |
| `POST /v1/backup-tenant` | see below | Runs the full pipeline and returns artifact metadata. |

### `POST /v1/backup-tenant`

```jsonc
{
  "tenantId":     "uuid",          // logged for traceability
  "dbName":       "tenant-acme",   // pg_dump target
  "slug":         "acme",          // filestore subdirectory under /var/lib/odoo/filestore
  "dekHex":       "<64 hex chars>", // 32-byte AES-256-GCM key, plaintext (TLS-encrypted in transit)
  "s3Bucket":     "...",           // destination WARM bucket
  "s3Key":        "tenants/<id>/warm/<date>.enc"
}
```

Response:

```jsonc
{
  "storageUrl":  "s3://.../tenants/.../warm/...enc",
  "sizeBytes":   1234567,
  "sha256Hex":   "<64 hex chars>",
  "nonceHex":    "<24 hex chars>",
  "tagHex":      "<32 hex chars>",
  "lsn":         "0/1F2C3D40"
}
```

## Encryption file format

```
[32B encrypted header:
   16B ASCII magic "ODOO-SAAS-PKG-V1"
    8B LE u64 dump.size
    8B LE u64 filestore.size]
[encrypted pg_dump bytes (dump.size)]
[encrypted filestore tar bytes (filestore.size)]
[16B GCM auth tag]
```

The format intentionally matches the one documented in the control plane's
`packages/workflows/src/tenant-backup-daily.ts::runEncryptPackage` from
before this service existed, so restore tooling that targets that format
keeps working.

## Env vars

| Var | Required | Purpose |
|---|---|---|
| `BACKUP_RUNNER_TOKEN` | yes | Bearer token; rotate quarterly. |
| `PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD` | yes | pg_dump connection. |
| `FILESTORE_BASE` | yes | Path to mounted filestore root (typically `/var/lib/odoo/filestore`). |
| `AWS_REGION` | yes | S3 region. |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | yes | IAM creds for S3 PutObject. Use the `pgbackrest_railway` / `pgbackrest_fly` IAM users from the Terraform output (they already have the right S3 permissions). |
| `PORT` | no | Default 8080. |

## Deployment model

The runner sits in the same Railway project / Fly app group as Postgres + Odoo
so its private network reaches both. On Railway it's a service; on Fly it's
its own app. Mount the Odoo filestore volume as read-only at `FILESTORE_BASE`
(specific to platform — see the per-platform manifests).

Mounts on Fly require the volume to be in the same region as the Postgres
+ Odoo apps. Mounts on Railway require the volume to be attached to this
service in the dashboard.

## What's NOT here (Phase 1 simplification)

- **Atomic pgdata + filestore snapshot.** The plan calls for ZFS subvolume
  snapshots or pgBackRest's start/stop_backup wrapper to guarantee
  point-in-time consistency between the SQL dump and the filestore tar.
  This runner produces both serially; a tenant writing to filestore
  between pg_dump start and tar finish would produce an inconsistent
  package. Acceptable for Phase 1 pilot (low concurrent write tenants);
  must be fixed before GA. Tracked as a Phase 2 task.
- **`/v1/compliance-snapshot`** for the COLD-tier DIAN-only JSONL package.
  Designed separately in the plan; lives in its own future endpoint.
- **`/v1/restore-tenant`** for PITR restore. Manual operator workflow today.
