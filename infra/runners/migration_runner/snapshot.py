"""Snapshot helper — wraps pgBackRest for the pre-migration safety net.

Two implementation strategies, selected via env:

- SNAPSHOT_MODE=cli — call `pgbackrest --stanza=<stanza> backup --type=incr`
  directly. Used when the runner has direct shell access to a node where
  pgbackrest is configured (Railway: backups run inside the postgres
  service; Fly: a sidecar).
- SNAPSHOT_MODE=http — POST to the existing `saas_filestore_backup` HTTP
  endpoint (HMAC-signed). Used when the runner runs on a separate
  machine from the backup service.

Both return a `snapshot_id` (the pgBackRest tag) that the rollback
path (Tier 5) consumes.

If `SNAPSHOT_MODE=skip` the call is a no-op returning a sentinel
'no-snapshot-<timestamp>' string — used in tests and in CI smokes
where pgBackRest isn't wired up yet.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import subprocess
import time
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


class SnapshotError(RuntimeError):
    """Snapshot operation failed in a non-recoverable way."""


@dataclass(frozen=True, slots=True)
class SnapshotResult:
    snapshot_id: str
    elapsed_seconds: float


def take_snapshot(
    *,
    tenant_slug: str,
    db_name: str,
    mode: Optional[str] = None,
    hmac_secret: Optional[str] = None,
    backup_service_url: Optional[str] = None,
    pgbackrest_stanza: Optional[str] = None,
) -> SnapshotResult:
    """Take a pre-migration snapshot. Returns the snapshot tag.

    Env-driven defaults so the runner just calls take_snapshot(slug, db).
    """
    mode = mode or os.environ.get('SNAPSHOT_MODE', 'skip')
    started = time.monotonic()
    if mode == 'skip':
        return SnapshotResult(
            snapshot_id=f'no-snapshot-{int(started)}',
            elapsed_seconds=0.0,
        )
    if mode == 'cli':
        stanza = pgbackrest_stanza or os.environ.get('PGBACKREST_STANZA', db_name)
        snapshot_id = _snapshot_via_cli(stanza)
        return SnapshotResult(snapshot_id=snapshot_id, elapsed_seconds=time.monotonic() - started)
    if mode == 'http':
        url = backup_service_url or os.environ.get('BACKUP_SERVICE_URL')
        secret = hmac_secret or os.environ.get('SAAS_BACKUP_HMAC_SECRET')
        if not url or not secret:
            raise SnapshotError(
                'SNAPSHOT_MODE=http requires BACKUP_SERVICE_URL + SAAS_BACKUP_HMAC_SECRET'
            )
        snapshot_id = _snapshot_via_http(
            url=url, secret=secret, tenant_slug=tenant_slug, db_name=db_name
        )
        return SnapshotResult(snapshot_id=snapshot_id, elapsed_seconds=time.monotonic() - started)
    raise SnapshotError(f'unknown SNAPSHOT_MODE={mode!r}')


def _snapshot_via_cli(stanza: str) -> str:
    """Run pgbackrest backup. Returns the backup label.

    The backup label is parsed from the last 'INFO: full|diff|incr
    backup: label = <label>' line in stdout.
    """
    try:
        result = subprocess.run(  # noqa: S603 — args are controlled
            ['pgbackrest', f'--stanza={stanza}', 'backup', '--type=incr'],
            check=True,
            capture_output=True,
            text=True,
            timeout=15 * 60,
        )
    except subprocess.CalledProcessError as exc:
        raise SnapshotError(
            f'pgbackrest exit {exc.returncode}: {(exc.stderr or "")[-2000:]}'
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise SnapshotError('pgbackrest timed out after 15 min') from exc
    label = _parse_backup_label(result.stdout)
    if not label:
        raise SnapshotError(
            f'pgbackrest produced no backup label in stdout; tail={result.stdout[-2000:]}'
        )
    return label


def _parse_backup_label(stdout: str) -> Optional[str]:
    for line in reversed(stdout.splitlines()):
        # pgbackrest's INFO line:
        # "INFO: full backup: label = 20260523-220000F"
        marker = 'backup: label = '
        idx = line.find(marker)
        if idx >= 0:
            return line[idx + len(marker) :].strip()
    return None


def _snapshot_via_http(*, url: str, secret: str, tenant_slug: str, db_name: str) -> str:
    """POST to the backup service. HMAC body signing matches the
    pattern saas_provisioning_gateway uses."""
    import urllib.request

    payload = json.dumps(
        {
            'tenant_slug': tenant_slug,
            'db_name': db_name,
            'reason': 'pre-migration',
        }
    ).encode('utf-8')
    signature = hmac.new(secret.encode('utf-8'), payload, hashlib.sha256).hexdigest()
    req = urllib.request.Request(  # noqa: S310 — controlled URL
        url=url.rstrip('/') + '/snapshot',
        data=payload,
        method='POST',
        headers={
            'Content-Type': 'application/json',
            'X-Signature': signature,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15 * 60) as resp:  # noqa: S310
            body = resp.read().decode('utf-8')
    except Exception as exc:  # urllib raises a number of distinct types
        raise SnapshotError(f'backup HTTP call failed: {exc}') from exc
    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        raise SnapshotError(f'backup service returned non-JSON: {body[:200]}') from exc
    snapshot_id = data.get('snapshot_id')
    if not snapshot_id or not isinstance(snapshot_id, str):
        raise SnapshotError(f'backup service response missing snapshot_id: {body[:200]}')
    return snapshot_id
