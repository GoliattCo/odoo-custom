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


# ── CLI entrypoint (used by rollback-prod.yml `tenant-restore` step) ───

def _lookup_plan(cur, job_id: str, previous_sha: str, actor: str) -> RollbackPlan:
    """Build a RollbackPlan from the job row + tenant row.

    Raises RollbackError if the job is unknown or the snapshot wasn't
    recorded (pre-Tier-7 jobs without snapshot_id can't be rolled back
    this way)."""
    cur.execute(
        """
        SELECT j.id::text, j.tenant_id::text, t.db_name, t.slug, j.snapshot_id
        FROM tenant_migration_jobs j
        JOIN tenants t ON t.id = j.tenant_id
        WHERE j.id = %s
        """,
        (job_id,),
    )
    row = cur.fetchone()
    if row is None:
        raise RollbackError(f'job {job_id} not found')
    _, tenant_id, db_name, slug, snapshot_id = row
    if not snapshot_id:
        raise RollbackError(
            f'job {job_id} has no snapshot_id — cannot restore from pgbackrest'
        )
    return RollbackPlan(
        job_id=job_id,
        tenant_id=tenant_id,
        tenant_db_name=db_name,
        snapshot_id=snapshot_id,
        previous_sha=previous_sha,
        reason=f'operator rollback to {previous_sha[:7]}',
        actor=actor,
    )


def _finalize_ok(cur, plan: RollbackPlan) -> None:
    """Revert tenants.last_migrated_sha, flip the job to 'rolled_back',
    and write the audit row. Single transaction so partial failures
    don't leave inconsistent state."""
    cur.execute(
        """
        UPDATE tenants
        SET last_migrated_sha = %s, updated_at = now()
        WHERE id = %s
        """,
        (plan.previous_sha, plan.tenant_id),
    )
    cur.execute(
        """
        UPDATE tenant_migration_jobs
        SET status = 'cancelled',
            finished_at = now(),
            error_excerpt = %s
        WHERE id = %s
        """,
        (f'rolled back to {plan.previous_sha[:7]} by {plan.actor}', plan.job_id),
    )
    cur.execute(
        """
        INSERT INTO saas_audit.event
            (actor_kind, actor_name, action, target_kind, target_id, sha, reason, payload)
        VALUES
            ('human', %s, 'tenant.migration_rolled_back', 'tenant', %s, %s, %s,
             jsonb_build_object(
                'job_id', %s,
                'snapshot_id', %s,
                'previous_sha', %s,
                'outcome', 'ok'
             ))
        """,
        (
            plan.actor,
            plan.tenant_id,
            plan.previous_sha,
            plan.reason,
            plan.job_id,
            plan.snapshot_id,
            plan.previous_sha,
        ),
    )


def cli(argv: Optional[list[str]] = None) -> int:
    """`python -m migration_runner.rollback <job_id> <previous_sha>`

    Reads CONTROL_PLANE_PG_DSN from env, opens a single connection,
    looks up the migration job + tenant, runs the pgBackRest restore
    via `run()`, and on success reverts tenants.last_migrated_sha +
    writes a saas_audit.event row. All DB writes are committed in one
    transaction so the audit row + sha revert are atomic.

    Exit codes:
      0  — restore + finalize succeeded.
      1  — usage error (missing args).
      2  — RollbackError raised (job missing, snapshot missing, etc).
      3  — pgbackrest restore returned status='restore_failed'.
      4  — pgbackrest snapshot tag absent (status='snapshot_missing').
    """
    import sys

    if argv is None:
        argv = sys.argv[1:]
    if len(argv) != 2:
        print(
            'usage: python -m migration_runner.rollback <job_id> <previous_sha>',
            file=sys.stderr,
        )
        return 1
    job_id, previous_sha = argv
    actor = os.environ.get('ROLLBACK_ACTOR') or os.environ.get('GITHUB_ACTOR', 'unknown')

    logging.basicConfig(
        level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s %(message)s'
    )

    dsn = os.environ.get('CONTROL_PLANE_PG_DSN')
    if not dsn:
        print('CONTROL_PLANE_PG_DSN not set', file=sys.stderr)
        return 1

    # Local import so unit tests can stub the module without pulling
    # psycopg. Matches the same import pattern as JobStore._connect.
    import psycopg

    conn = psycopg.connect(dsn, autocommit=False)
    try:
        with conn.cursor() as cur:
            try:
                plan = _lookup_plan(cur, job_id, previous_sha, actor)
            except RollbackError as exc:
                logger.error('%s', exc)
                conn.rollback()
                return 2
        # Snapshot restore happens OUTSIDE the DB transaction — it
        # shells out to pgbackrest and can take minutes/hours. We
        # also commit the lookup-side read-txn first so the pgbackrest
        # subprocess doesn't hold a transaction open against Neon.
        conn.commit()
        result = run(plan)
        if result.status == 'snapshot_missing':
            logger.error('snapshot %s missing — aborting', plan.snapshot_id)
            return 4
        if result.status == 'restore_failed':
            logger.error('pgbackrest restore failed for snapshot %s', plan.snapshot_id)
            return 3
        with conn.cursor() as cur:
            _finalize_ok(cur, plan)
        conn.commit()
    finally:
        conn.close()
    logger.info(
        'rollback OK job=%s tenant=%s previous_sha=%s',
        plan.job_id,
        plan.tenant_db_name,
        plan.previous_sha,
    )
    return 0


if __name__ == '__main__':
    import sys

    sys.exit(cli())
