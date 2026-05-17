# Goliatt Odoo Enterprise — Self-Host Install Guide

This is the install bundle for the enterprise self-host edition of Goliatt's Colombian-localized Odoo 19 distribution. The image embeds the standard Odoo plus Colombian DIAN e-invoicing addons; license checks happen against Goliatt's license authority over HTTPS every hour.

## What you'll receive from Goliatt

Out-of-band (email, encrypted channel) you'll get exactly five values:

| Variable | What it is | Sensitivity |
|---|---|---|
| `LICENSE_ID` | UUID identifying your license. | Treat as a customer ID — not secret per se, but not for public posting. |
| `SAAS_PROVISIONING_SECRET` | HMAC shared secret with the license authority. **Customer-specific** — yours alone. | Secret. Never commit, never log. |
| `ODOO_IMAGE_DIGEST` | sha256 of the image build your license is bound to (without the `sha256:` prefix). | Not secret. Pinning your install to a specific build. |
| `ADMIN_PASSWORD` | Odoo master / admin user password. Goliatt generates a strong random one; you should rotate it on first login. | Secret. |
| Image pull credentials (optional) | A GHCR PAT, if your image is in a private registry. | Secret. |

`LICENSE_AUTHORITY_URL` is `https://odoo-saas-admin.vercel.app` (not customer-specific, no need for delivery).

## Prerequisites

- Docker Engine ≥ 24 and Docker Compose v2.
- A PostgreSQL 14+ instance you control. RDS / Cloud SQL / self-managed all work. Database superuser or a user that can `CREATE DATABASE` + connect.
- Outbound HTTPS access from the Odoo host to `https://odoo-saas-admin.vercel.app` (the hourly license check, ~4 KB / call).
- A backup strategy for your Postgres + Odoo filestore. Goliatt does not back up self-host data.

## Install — `docker-compose.yml`

Copy this template, fill in the values you received, and save as `docker-compose.yml`:

```yaml
services:
  odoo:
    image: ghcr.io/<your-image-owner>/odoo-saas-odoo-enterprise:enterprise-v1
    restart: unless-stopped
    environment:
      # ── License binding (from Goliatt) ─────────────────────
      LICENSE_ID: "${LICENSE_ID}"
      LICENSE_AUTHORITY_URL: "https://odoo-saas-admin.vercel.app"
      SAAS_PROVISIONING_SECRET: "${SAAS_PROVISIONING_SECRET}"
      ODOO_IMAGE_DIGEST: "${ODOO_IMAGE_DIGEST}"

      # ── Odoo runtime ──────────────────────────────────────
      ADMIN_PASSWORD: "${ADMIN_PASSWORD}"
      # CRITICAL: the license gate must be installed at first-boot
      # or the database refuses to bootstrap.
      INIT_MODULES: "saas_license_gate,base,web"
      TARGET_DB: "${ODOO_DB_NAME}"          # e.g. "production"
      WORKERS: "4"                          # tune to host cores
      PLATFORM: "customer-self-host"

      # ── Your Postgres ─────────────────────────────────────
      PGHOST: "${PG_HOST}"
      PGPORT: "${PG_PORT:-5432}"
      PGUSER: "${PG_USER}"
      PGPASSWORD: "${PG_PASSWORD}"

    ports:
      - "8069:8069"      # web UI; put TLS-terminating reverse proxy in front
      - "8072:8072"      # longpolling (chat / live updates)

    volumes:
      - odoo-filestore:/var/lib/odoo
    healthcheck:
      test: ["CMD", "curl", "-fsS", "http://localhost:8069/saas/health"]
      interval: 30s
      timeout: 5s
      retries: 5

volumes:
  odoo-filestore:
```

## `.env` template

Save alongside the compose file (gitignore it):

```bash
# === From Goliatt (out-of-band) ===
LICENSE_ID=
SAAS_PROVISIONING_SECRET=
ODOO_IMAGE_DIGEST=
ADMIN_PASSWORD=

# === Yours ===
ODOO_DB_NAME=production
PG_HOST=
PG_PORT=5432
PG_USER=
PG_PASSWORD=
```

## First boot

```bash
docker compose pull
docker compose up -d
docker compose logs -f odoo
```

On first start Odoo initializes the database, installs `saas_license_gate` + `base` + `web`, and runs the addon's `pre_init_hook`. The hook:

1. Verifies `LICENSE_ID` is set; **the database refuses to initialize if not.**
2. Reads the public key from `/etc/saas-license-pubkey.pem` (baked into the image).
3. Calls Goliatt's `/api/internal/license/check` with your HMAC. The response is Ed25519-signed; the addon verifies the signature locally.
4. If the response says `valid=true` → install proceeds.
5. Stores the verdict in `ir.config_parameter` for the addon's hourly cron.

Once you see `Worker WorkerHTTP alive` in the logs and `curl http://localhost:8069/saas/health` returns 200, log in at `http://<host>:8069/web/login` as user `admin` with `ADMIN_PASSWORD`, and rotate the password through Preferences → Account Security.

## Behavior over time

- **Hourly cron** re-checks the license. If Goliatt has revoked or your term has expired, write-heavy models (`account.move`, `sale.order`, `stock.picking`) flip to read-only and a banner appears in the system bar.
- **Grace mode** activates between `expires_at` and `grace_until` (typically 14 days). Only `account.move` stays writable, so you can finish closing the books on the period you've paid for.
- **Stale checks** (no successful check in 14 days, e.g. network outage to Goliatt) flip the state to read-only as a fail-safe. Once Goliatt is reachable again, the next hourly tick restores write access automatically.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `pre_init_hook: LICENSE_ID unset` | Compose env didn't propagate. | Confirm `.env` is in the compose-file directory and `LICENSE_ID` is non-empty. Re-run `docker compose up -d` after fixing. |
| `License invalid: signature_verification_failed` banner | Image was tampered with, or you're running an unsigned variant. | Don't proceed. Pull the image fresh with `docker compose pull --force` and verify the digest matches your `ODOO_IMAGE_DIGEST`. Contact support if it persists. |
| `License invalid: image_sha256_mismatch` banner | You pulled a newer image tag than the one your license was minted against. | Either pin back to your original `ODOO_IMAGE_DIGEST` or ask Goliatt to re-mint against the new digest. |
| `License invalid: expires_at` banner, no write access | License term ended without renewal. | Pay invoice; Goliatt extends the term; next hourly tick restores access. While in grace, only `account.move` stays writable. |
| `503 license-signing-key-unset` in addon logs | Goliatt-side env-var issue. | Open a ticket — this is on Goliatt to fix; not actionable from your side. |
| Slow logins, sudden HTTP 500s after a year | Postgres autovacuum lag on long-running install. | Standard Odoo Postgres maintenance — VACUUM ANALYZE on `account_move_line` typically helps. |

## Backup recommendations

You own the data; you own the backups. Minimum:

- `pg_dump --format=custom` of your Odoo DB, daily, retained 30 days. Encrypt at rest.
- `tar -czf` of `odoo-filestore` (mapped to `/var/lib/odoo` in the container), daily, retained 30 days.
- Tested restore drill, quarterly.

A backup that's never been restored isn't a backup.

## Support

- Operational issues / outages: `support@goliatt.co`
- License questions (renewals, transfers, new seats): `licensing@goliatt.co`
- Security concerns: `security@goliatt.co`

Include your `LICENSE_ID` in every ticket. Don't include `SAAS_PROVISIONING_SECRET` or `ADMIN_PASSWORD` — Goliatt support never needs them.
