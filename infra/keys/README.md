# License signing keys

The control-plane `/api/internal/license/check` endpoint signs every
response with an Ed25519 keypair. The `saas_license_gate` Odoo addon
embeds the **public** half of this keypair and verifies the signature
on every license check — so a forged response (or tampered transit
layer) cannot grant validity to an addon that the operator hasn't
actually licensed.

## Files in this directory

| File | When it exists | Notes |
|---|---|---|
| `license-signing-pubkey.dev.pem` | **Before** the production rotation has been performed. | Generated during Phase 4.1 scaffolding; the private half was printed to a shell scrollback and is **not safe** for production. The Dockerfile's `ARG LICENSE_PUBKEY_FILE` defaults to this file so CI can build out-of-the-box. |
| `license-signing-pubkey.pem` | **After** the operator completes Step 1 of `infra/runbooks/enterprise-onboarding.md`. | The production pubkey. Both `Dockerfile` and `.github/workflows/ghcr-publish.yml` (the `publish-enterprise` job) reference this path. |

The dev key is `git rm`'d as part of the rotation commit; both files are not expected to coexist.

## Rotation

The full operator procedure — generate keypair, commit pubkey + flip Dockerfile default ARG, set `LICENSE_SIGNING_PRIVATE_KEY_B64` in Vercel, destroy local private key, smoke-test — lives in `infra/runbooks/enterprise-onboarding.md` § "Step 1 — Rotate the Ed25519 signing key". Do not duplicate the procedure here; one source of truth.

To re-rotate (e.g. annual rotation, suspected compromise), follow the same Step 1, then trigger a fresh enterprise image build by pushing a new `enterprise-v*` tag (Step 2 in the same runbook).

## Why Ed25519 (not RSA)

- 64-byte signatures vs RSA-2048's 256 bytes → smaller wire format, easier to log/audit.
- Deterministic signing — same payload always produces the same signature, which makes test fixtures stable.
- No PKCS#11 / OAEP padding gotchas; the addon's `cryptography` verification call is two lines.
- Native Node.js support (no extra deps in the control-plane).
