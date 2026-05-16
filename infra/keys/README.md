# License signing keys

The control-plane `/api/internal/license/check` endpoint signs every
response with an Ed25519 keypair. The `saas_license_gate` Odoo addon
embeds the **public** half of this keypair and verifies the signature
on every license check — so a forged response (or tampered transit
layer) cannot grant validity to an addon that the operator hasn't
actually licensed.

## Files

- `license-signing-pubkey.dev.pem` — Ed25519 public key used by the
  saas_license_gate addon **in development and CI only**. This file was
  generated during Phase 4.1 scaffolding and the private half was
  printed to a shell scrollback, so it is **not safe** for production
  use.

## Production rotation procedure

Before the first paying enterprise customer is onboarded, the operator
MUST replace this key with a freshly generated production keypair:

```bash
# 1. Generate a fresh Ed25519 keypair on a trusted workstation.
node -e "
const c = require('crypto');
const { publicKey, privateKey } = c.generateKeyPairSync('ed25519');
require('fs').writeFileSync('/tmp/license-priv.pem',
  privateKey.export({ type: 'pkcs8', format: 'pem' }));
require('fs').writeFileSync('/tmp/license-pub.pem',
  publicKey.export({ type: 'spki', format: 'pem' }));
console.log('wrote /tmp/license-priv.pem and /tmp/license-pub.pem');
"

# 2. Commit the public half (this directory) — replace the dev file.
cp /tmp/license-pub.pem infra/keys/license-signing-pubkey.pem
git add infra/keys/license-signing-pubkey.pem
git rm infra/keys/license-signing-pubkey.dev.pem  # if still present
git commit -m "chore(license): rotate license signing public key"

# 3. Set the private half in Vercel (admin app, production only).
#    Pipe to base64 so the multiline PEM survives env var transport.
base64 < /tmp/license-priv.pem | tr -d '\n' | pbcopy
# Then in Vercel dashboard or via CLI:
vercel env add LICENSE_SIGNING_PRIVATE_KEY_B64 production
# Paste from clipboard. Apply same key to preview if you want preview-
# environment license checks to work.

# 4. Rebuild any released addon images so they embed the new pub key.
#    The addon reads /etc/saas-license-pubkey.pem at runtime — that
#    file is COPY'd in from infra/keys/license-signing-pubkey.pem
#    during the Docker build. Pin to the GHCR tag with the rotated key.

# 5. Securely destroy the private key file:
shred -uz /tmp/license-priv.pem /tmp/license-pub.pem  # Linux
# OR
rm -P /tmp/license-priv.pem /tmp/license-pub.pem      # macOS

# 6. Note the rotation timestamp in a memory entry (e.g.
#    reference_license_key_rotation.md) so the next operator knows
#    when the current keypair came into service.
```

## Why Ed25519 (not RSA)

- 64-byte signatures vs RSA-2048's 256 bytes → smaller wire format,
  easier to log/audit.
- Deterministic signing — same payload always produces the same
  signature, which makes test fixtures stable.
- No PKCS#11 / OAEP padding gotchas; the addon's `cryptography`
  verification call is two lines.
- Native Node.js support (no extra deps in the control-plane).
