# GitHub Actions secrets

The `.github/workflows/ci.yml` cross-platform deploy gate needs these
repository secrets configured at **Settings → Secrets and variables →
Actions → Repository secrets**.

| Secret | Scope | Where to get it |
|---|---|---|
| `RAILWAY_TOKEN` | Repo | Railway dashboard → Project → Tokens → "Create token". Use a **team/project token**, not your personal token. Limit to the staging environment. |
| `RAILWAY_ODOO_SERVICE_ID` | Repo | Railway dashboard → Service → Settings → service ID at the top of the page. Picks up the staging Odoo pool service. |
| `FLY_API_TOKEN` | Repo | `fly auth token` after `fly auth login` as the deploy user. Scope to the org if possible. |

## Environments

The workflow uses two GitHub Environments to gate deploys:

- `staging-railway`
- `staging-fly`

Configure at **Settings → Environments**. For each, you can:

- Add reviewers if you want manual approval before each deploy.
- Set environment-specific secrets (overrides the repo-level ones).
- Set a wait timer (e.g., 5 minutes between merges and deploys).

For Phase 1 pilot, leave reviewers off — automatic deploys on merge to main.

## Why two environments instead of one?

Railway and Fly have separate failure modes, separate auth, separate
quotas. Splitting into two environments means a Fly token rotation
doesn't accidentally invalidate Railway deploys, and vice versa. The
`cross-platform-gate` job at the end of the workflow stitches them back
together to enforce parity.

## Rotating tokens

Quarterly:

```
# Railway
# Railway dashboard → Project → Tokens → revoke old token, create new one
# Update RAILWAY_TOKEN in GitHub repo secrets

# Fly
fly tokens create deploy --name "ci-rotated-YYYY-MM-DD"
# Update FLY_API_TOKEN in GitHub repo secrets, then revoke the old one:
fly tokens revoke <old-token-id>
```

## Not yet in CI

- **Vercel deploy** for the control plane lives in the OTHER repo
  (`/Volumes/SATECHI2TB/userfolder/Odoo-control-plane/`). Vercel
  auto-deploys per PR from that repo; no GitHub Actions setup needed
  there beyond a typecheck workflow.
- **AWS credentials for `terraform apply`** are not in CI. Terraform
  applies are done locally by an operator. Adding `terraform plan`
  to PRs is a future enhancement.
- **Helm chart / GHCR signed image push** for the enterprise self-host
  artifact (Phase 4) — separate workflow when we get there.
