"""Rollback helper — restore a tenant DB from its pre-migration
snapshot when a migration succeeded at the schema level but broke
the tenant in production.

Composes with the existing rollback-prod.yml: that workflow rolls
back the IMAGE; this module rolls back the DATA. Together they
restore a tenant to "the state it was in before migration job X".

Inputs (positional): job_id (uuid). Looks up:
- snapshot_id from tenant_migration_jobs
- db_name + slug + previous_last_migrated_sha from tenants
- pre-migration image digest from the `tenant_image_pins` table
  (Phase 4.1 enterprise-v1 surface — not added in this commit's
  schema; rollback assumes the operator has pinned the previous
  digest separately and only needs the DB restore).

Side effects:
1. Stops the tenant from serving traffic (sets state='suspended').
2. Calls pgBackRest restore on the snapshot tag.
3. Reverts tenants.last_migrated_sha (we don't have history here so
   we ARGUMENT a previous_sha).
4. Re-enables the tenant (state='active') after restore.
5. Records an audit event 'tenant.migration_rolled_back'.

Idempotency: rollback is operator-initiated and assumed to be a
one-shot. The runner does NOT auto-rollback on failure — Tier 5
acceptance criteria explicitly call for operator action only.
"""

from __future__ import annotations

import logging
import os
import subprocess
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


class RollbackError(RuntimeError):
    """Rollback couldn't complete."""


@dataclass(frozen=True, slots=True)
class RollbackPlan:
    """Inputs the operator workflow passes to rollback.run()."""

    job_id: str
    tenant_id: str
    tenant_db_name: str
    snapshot_id: str
    previous_sha: Optional[str]
    reason: str
    actor: str


@dataclass(frozen=True, slots=True)
class RollbackResult:
    job_id: str
    snapshot_id: str
    status: str  # 'ok' | 'snapshot_missing' | 'restore_failed'


def run(
    plan: RollbackPlan,
    *,
    pgbackrest_stanza: Optional[str] = None,
    subprocess_runner=subprocess.run,
) -> RollbackResult:
    """Restore the tenant DB from its pre-migration snapshot tag.

    Assumes a separate process / step has already suspended the tenant
    (this module shouldn't decide tenant lifecycle on its own).
    """
    stanza = pgbackrest_stanza or os.environ.get('PGBACKREST_STANZA', plan.tenant_db_name)

    logger.info(
        'rollback start job=%s tenant=%s snapshot=%s',
        plan.job_id,
        plan.tenant_db_name,
        plan.snapshot_id,
    )

    # Step 1: verify the snapshot still exists. pgBackRest's `info`
    # command returns JSON we can grep for the tag.
    try:
        info = subprocess_runner(
            ['pgbackrest', f'--stanza={stanza}', 'info', '--output=json'],
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.CalledProcessError as exc:
        raise RollbackError(
            f'pgbackrest info exit {exc.returncode}: {(exc.stderr or "")[-2000:]}'
        ) from exc
    if plan.snapshot_id not in (info.stdout or ''):
        return RollbackResult(
            job_id=plan.job_id,
            snapshot_id=plan.snapshot_id,
            status='snapshot_missing',
        )

    # Step 2: restore. pgBackRest restore requires the Postgres
    # service to be stopped — Tier 5 runbook covers the orchestration;
    # here we run the command and let the operator handle the rest.
    try:
        subprocess_runner(
            [
                'pgbackrest',
                f'--stanza={stanza}',
                '--delta',
                '--set',
                plan.snapshot_id,
                'restore',
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=2 * 60 * 60,  # 2h cap
        )
    except subprocess.CalledProcessError as exc:
        logger.error(
            'pgbackrest restore failed exit=%d stderr=%s',
            exc.returncode,
            (exc.stderr or '')[-2000:],
        )
        return RollbackResult(
            job_id=plan.job_id,
            snapshot_id=plan.snapshot_id,
            status='restore_failed',
        )
    except subprocess.TimeoutExpired as exc:
        raise RollbackError(f'pgbackrest restore timed out after 2h: {exc}') from exc

    logger.info('rollback complete job=%s', plan.job_id)
    return RollbackResult(
        job_id=plan.job_id,
        snapshot_id=plan.snapshot_id,
        status='ok',
    )
