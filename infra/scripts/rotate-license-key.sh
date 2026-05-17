#!/usr/bin/env bash
# Phase 4.1 — One-shot rotation of the Ed25519 license signing keypair.
#
# Automates Step 1 of infra/runbooks/enterprise-onboarding.md end-to-end:
#   1. Generate a fresh Ed25519 keypair inside a chmod-700 temp dir.
#   2. Commit + push the new pubkey to the data-plane repo, git rm the
#      dev pubkey (if present), flip the Dockerfile default ARG.
#   3. base64-encode the private key and set LICENSE_SIGNING_PRIVATE_KEY_B64
#      in Vercel (admin app, production env). Removes the existing var
#      first so re-rotations are idempotent.
#   4. Trigger a Vercel redeploy so the new env reaches runtime.
#   5. Smoke-test /api/internal/license/check; expect anything except 503
#      license-signing-key-unset.
#   6. Securely shred the private key on EXIT — even if any step above
#      fails. The private key NEVER leaves the temp dir.
#
# Safe to run again to perform a re-rotation; the same idempotent behavior
# kicks in (pubkey content changes, Vercel var rm-then-add).
#
# Refuses to run inside CI; private keys must only be generated on a
# trusted operator workstation.
#
# Required tools: node, openssl, git, gh (optional, for push verification),
#                 vercel CLI logged in to the admin project.
# Optional env:
#   DATA_PLANE_REPO       — defaults to $HOME/Odoo
#   CONTROL_PLANE_ADMIN   — defaults to $HOME/Odoo-control-plane/apps/admin
#   LICENSE_AUTHORITY_URL — defaults to https://odoo-saas-admin.vercel.app
#   SAAS_PROVISIONING_SECRET — needed for the smoke test (skipped if unset)
#   SKIP_PUSH=1           — commit locally but don't push (caller will push)
#   SKIP_REDEPLOY=1       — skip Vercel redeploy step
#   SKIP_SMOKE=1          — skip the /v1/check smoke test

set -euo pipefail

# ---------- pre-flight ----------

if [[ "${CI:-}" == "true" || -n "${GITHUB_ACTIONS:-}" ]]; then
  echo "ERROR: refusing to run inside CI; rotate keys only on a trusted workstation" >&2
  exit 2
fi

DATA_PLANE_REPO="${DATA_PLANE_REPO:-$HOME/Odoo}"
CONTROL_PLANE_ADMIN="${CONTROL_PLANE_ADMIN:-$HOME/Odoo-control-plane/apps/admin}"
LICENSE_AUTHORITY_URL="${LICENSE_AUTHORITY_URL:-https://odoo-saas-admin.vercel.app}"

if [[ ! -d "$DATA_PLANE_REPO/infra/keys" ]]; then
  echo "ERROR: data-plane repo not found at $DATA_PLANE_REPO" >&2
  echo "       override with DATA_PLANE_REPO=..." >&2
  exit 1
fi
if [[ ! -d "$CONTROL_PLANE_ADMIN" ]]; then
  echo "ERROR: control-plane admin app not found at $CONTROL_PLANE_ADMIN" >&2
  echo "       override with CONTROL_PLANE_ADMIN=..." >&2
  exit 1
fi

for tool in node openssl git curl; do
  command -v "$tool" >/dev/null 2>&1 || { echo "ERROR: $tool required"; exit 1; }
done
if ! command -v vercel >/dev/null 2>&1; then
  echo "ERROR: vercel CLI required (npm i -g vercel@latest)" >&2
  exit 1
fi
if ! (cd "$CONTROL_PLANE_ADMIN" && vercel whoami >/dev/null 2>&1); then
  echo "ERROR: vercel CLI not authenticated; run 'vercel login' first" >&2
  exit 1
fi

# Pick a shred command for the platform
if command -v shred >/dev/null 2>&1; then
  SHRED_CMD=(shred -uz)
else
  SHRED_CMD=(rm -P)   # macOS — overwrite then unlink
fi

# ---------- workspace ----------

WORK="$(mktemp -d "${TMPDIR:-/tmp}/license-rotate-XXXXXX")"
chmod 700 "$WORK"
PRIV="$WORK/license-priv.pem"
PUB="$WORK/license-pub.pem"

cleanup() {
  local rc=$?
  if [[ -f "$PRIV" ]]; then
    echo "==> shredding $PRIV"
    "${SHRED_CMD[@]}" "$PRIV" 2>/dev/null || true
  fi
  rm -f "$PUB" 2>/dev/null || true
  rmdir "$WORK" 2>/dev/null || true
  exit $rc
}
trap cleanup EXIT INT TERM

# ---------- confirm ----------

cat <<EOF
================================================================
  Phase 4.1 — License signing key rotation
================================================================
Data-plane repo:    $DATA_PLANE_REPO
Control-plane app:  $CONTROL_PLANE_ADMIN
License authority:  $LICENSE_AUTHORITY_URL
Temp dir:           $WORK  (chmod 700, shredded on exit)

Will:
  A. Generate fresh Ed25519 keypair (private key stays in temp dir)
  B. Commit + push pubkey to data plane, swap dev → prod, flip Dockerfile ARG
  C. Set LICENSE_SIGNING_PRIVATE_KEY_B64 in Vercel (production)
  D. Redeploy admin app
  E. Smoke-test /api/internal/license/check
  F. Shred private key

EOF

read -r -p "Proceed? Type ROTATE to confirm: " confirm
[[ "$confirm" == "ROTATE" ]] || { echo "aborted"; exit 1; }

# ---------- A. generate keypair ----------

echo
echo "==> A. Generating Ed25519 keypair"
node - <<NODE
const c = require('crypto');
const fs = require('fs');
const { publicKey, privateKey } = c.generateKeyPairSync('ed25519');
fs.writeFileSync('$PRIV',
  privateKey.export({ type: 'pkcs8', format: 'pem' }),
  { mode: 0o600 });
fs.writeFileSync('$PUB',
  publicKey.export({ type: 'spki', format: 'pem' }),
  { mode: 0o644 });
NODE
[[ -s "$PRIV" && -s "$PUB" ]] || { echo "ERROR: keypair generation produced empty files"; exit 1; }
chmod 600 "$PRIV"

# ---------- B. data-plane rotation commit ----------

echo
echo "==> B. Data-plane rotation commit"
cd "$DATA_PLANE_REPO"

current_branch=$(git rev-parse --abbrev-ref HEAD)
if [[ "$current_branch" != "main" ]]; then
  echo "    WARN: not on main; current branch is '$current_branch'"
  read -r -p "    Continue anyway? [y/N] " ok
  [[ "$ok" =~ ^[Yy]$ ]] || exit 1
fi

if ! git diff --quiet HEAD -- infra/keys Dockerfile; then
  echo "ERROR: uncommitted changes in infra/keys or Dockerfile" >&2
  git status --short -- infra/keys Dockerfile >&2
  exit 1
fi

cp "$PUB" infra/keys/license-signing-pubkey.pem
chmod 644 infra/keys/license-signing-pubkey.pem

if [[ -f infra/keys/license-signing-pubkey.dev.pem ]]; then
  git rm infra/keys/license-signing-pubkey.dev.pem
fi

# Flip Dockerfile ARG default. Idempotent — sed re-runs are no-ops once flipped.
sed -i.bak \
  's|infra/keys/license-signing-pubkey\.dev\.pem|infra/keys/license-signing-pubkey.pem|g' \
  Dockerfile
rm -f Dockerfile.bak

if ! grep -q "ARG LICENSE_PUBKEY_FILE=infra/keys/license-signing-pubkey\.pem" Dockerfile; then
  echo "ERROR: Dockerfile ARG flip didn't take" >&2
  # Best-effort rollback
  git checkout -- Dockerfile 2>/dev/null || true
  rm -f infra/keys/license-signing-pubkey.pem
  exit 1
fi

git add infra/keys/license-signing-pubkey.pem Dockerfile

if git diff --cached --quiet; then
  echo "    (no staged changes — pubkey may already match; skipping commit)"
else
  git commit -m "chore(license): rotate signing key to production"
fi

if [[ "${SKIP_PUSH:-0}" == "1" ]]; then
  echo "    SKIP_PUSH=1 set; not pushing (do it yourself)"
else
  read -r -p "    Push to origin/$current_branch now? [Y/n] " push_ok
  if [[ -z "${push_ok// }" || "$push_ok" =~ ^[Yy]$ ]]; then
    git push origin "$current_branch"
  else
    echo "    (push skipped — remember to push manually)"
  fi
fi

# ---------- C. Vercel env ----------

echo
echo "==> C. Setting LICENSE_SIGNING_PRIVATE_KEY_B64 in Vercel (production)"
cd "$CONTROL_PLANE_ADMIN"

priv_b64=$(base64 < "$PRIV" | tr -d '\n')

if vercel env ls production 2>/dev/null | grep -q "LICENSE_SIGNING_PRIVATE_KEY_B64"; then
  echo "    existing var found; removing first"
  yes | vercel env rm LICENSE_SIGNING_PRIVATE_KEY_B64 production >/dev/null 2>&1 || true
fi

# `vercel env add` reads value from stdin when not on a TTY
printf '%s\n' "$priv_b64" | vercel env add LICENSE_SIGNING_PRIVATE_KEY_B64 production >/dev/null
echo "    set."
unset priv_b64

# ---------- D. redeploy ----------

if [[ "${SKIP_REDEPLOY:-0}" == "1" ]]; then
  echo "==> D. SKIP_REDEPLOY=1; skipping redeploy"
else
  echo
  echo "==> D. Triggering Vercel redeploy"
  # Find latest Ready production deployment and redeploy it (carries the
  # new env without a rebuild).
  #
  # Two gotchas baked into this awk:
  #   1. Vercel CLI writes the deployment table to STDERR — `2>&1` is
  #      required; `2>/dev/null` returns an empty stream.
  #   2. Status column reads "● Ready" (capitalized), Environment column
  #      reads "Production" — match the actual casing, not READY/production.
  latest_prod=$(vercel ls --prod 2>&1 \
    | awk '/Ready/ && /Production/ {for (i=1;i<=NF;i++) if ($i ~ /^https?:\/\//) {print $i; exit}}')
  if [[ -n "$latest_prod" ]]; then
    echo "    redeploying $latest_prod"
    # No --yes flag; `vercel redeploy` rejects it in CLI v50.x.
    vercel redeploy "$latest_prod" --target=production
  else
    # No fallback to `vercel deploy --prod` — that command has a known
    # monorepo gotcha where, when run from apps/admin in a project whose
    # Root Directory is also apps/admin, it tries to deploy
    # apps/admin/apps/admin and errors out. Better to fail loudly so the
    # operator can redeploy manually from the Vercel dashboard.
    echo "    ERROR: couldn't auto-detect latest production deployment URL." >&2
    echo "    Redeploy manually:" >&2
    echo "      cd $CONTROL_PLANE_ADMIN" >&2
    echo "      vercel ls --prod   # copy the topmost Ready URL" >&2
    echo "      vercel redeploy <url> --target=production" >&2
    exit 4
  fi
fi

# ---------- E. smoke test ----------

if [[ "${SKIP_SMOKE:-0}" == "1" ]]; then
  echo "==> E. SKIP_SMOKE=1; skipping smoke test"
elif [[ -z "${SAAS_PROVISIONING_SECRET:-}" ]]; then
  echo
  echo "==> E. SAAS_PROVISIONING_SECRET not set; skipping smoke test"
  echo "       To smoke-test manually:"
  echo "         SAAS_PROVISIONING_SECRET=… infra/scripts/license-cli.sh list-by-customer test"
else
  echo
  echo "==> E. Smoke-testing $LICENSE_AUTHORITY_URL/api/internal/license/check"
  echo "       (giving redeploy 20s to settle)"
  sleep 20

  ts=$(date +%s)
  body="{\"license_id\":\"00000000-0000-0000-0000-000000000000\",\"image_sha256\":\"deadbeef\",\"machine_id\":\"rotation-smoke\",\"timestamp\":$ts}"
  sig=$(printf '%s.%s' "$ts" "$body" \
    | openssl dgst -sha256 -hmac "$SAAS_PROVISIONING_SECRET" \
    | awk '{print $2}')

  resp=$(mktemp "$WORK/smoke-resp-XXXXXX")
  code=$(curl -sS -o "$resp" -w '%{http_code}' \
    -X POST "$LICENSE_AUTHORITY_URL/api/internal/license/check" \
    -H "content-type: application/json" \
    -H "x-saas-timestamp: $ts" \
    -H "x-saas-signature: sha256=$sig" \
    --data "$body")

  case "$code" in
    200|404)
      echo "       OK — endpoint responded with $code (signing key is wired)" ;;
    503)
      if grep -q "license-signing-key-unset" "$resp" 2>/dev/null; then
        echo "       FAIL — 503 license-signing-key-unset: env var didn't reach runtime" >&2
        echo "       Body: $(cat "$resp")" >&2
        exit 3
      else
        echo "       WARN — 503 but not the signing-key error:" >&2
        cat "$resp" >&2
      fi
      ;;
    *)
      echo "       WARN — unexpected $code; investigate manually:" >&2
      cat "$resp" >&2
      ;;
  esac
fi

echo
echo "==> Done. Private key will be shredded on exit."
