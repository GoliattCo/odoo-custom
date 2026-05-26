"""Tests for `python -m migration_runner.rollback` CLI.

The CLI orchestrates: argv parse → DB lookup → pgbackrest restore
(via rollback.run()) → atomic finalize (revert last_migrated_sha +
audit row). These tests stub psycopg + rollback.run so we don't need
a real DB or pgbackrest binary.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import patch

import pytest

from migration_runner import rollback as rb


@dataclass
class _FakeCursor:
    fetch_one: Any = None
    executed: list = field(default_factory=list)

    def execute(self, sql, params=()):
        self.executed.append((' '.join(sql.split()), params))

    def fetchone(self):
        return self.fetch_one

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return None


@dataclass
class _FakeConn:
    cur: _FakeCursor
    commits: int = 0
    rollbacks: int = 0
    closed: bool = False

    def cursor(self):
        return self.cur

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


def _job_row(*, snapshot_id='snap-pre-migration'):
    return (
        'job-uuid',
        'tenant-uuid',
        'acme_db',
        'acme',
        snapshot_id,
    )


class TestCliUsage:
    def test_missing_args_exits_1(self) -> None:
        assert rb.cli([]) == 1
        assert rb.cli(['only-one']) == 1
        assert rb.cli(['too', 'many', 'args']) == 1


class TestCliMissingDsn:
    def test_no_dsn_exits_1(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv('CONTROL_PLANE_PG_DSN', raising=False)
        assert rb.cli(['job', 'sha']) == 1


class TestCliHappyPath:
    def test_runs_finalize_and_commits(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv('CONTROL_PLANE_PG_DSN', 'postgresql://fake')
        monkeypatch.setenv('GITHUB_ACTOR', 'octocat')
        cur = _FakeCursor(fetch_one=_job_row())
        conn = _FakeConn(cur=cur)

        with patch('psycopg.connect', return_value=conn), patch.object(
            rb,
            'run',
            return_value=rb.RollbackResult(
                job_id='job-uuid',
                snapshot_id='snap-pre-migration',
                status='ok',
            ),
        ) as run_mock:
            rc = rb.cli(['job-uuid', '886bf8b'])

        assert rc == 0
        # run() called once with a RollbackPlan built from the row + actor
        assert run_mock.call_count == 1
        plan_arg = run_mock.call_args[0][0]
        assert plan_arg.job_id == 'job-uuid'
        assert plan_arg.tenant_db_name == 'acme_db'
        assert plan_arg.snapshot_id == 'snap-pre-migration'
        assert plan_arg.previous_sha == '886bf8b'
        assert plan_arg.actor == 'octocat'

        # Three UPDATE/INSERTs in finalize_ok: tenants, job, audit.event
        finalize_sqls = [c[0] for c in cur.executed if 'UPDATE' in c[0] or 'INSERT INTO' in c[0]]
        assert len(finalize_sqls) >= 3
        assert any('UPDATE tenants' in s for s in finalize_sqls)
        assert any('UPDATE tenant_migration_jobs' in s for s in finalize_sqls)
        assert any('INSERT INTO saas_audit.event' in s for s in finalize_sqls)

        # Two commits: lookup-side (released before the long-running
        # pgbackrest subprocess so no txn sits open against Neon for
        # hours) and finalize-side (atomic last_migrated_sha bump +
        # audit row). Connection closed in finally.
        assert conn.commits == 2
        assert conn.rollbacks == 0
        assert conn.closed is True


class TestCliJobNotFound:
    def test_returns_2(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv('CONTROL_PLANE_PG_DSN', 'postgresql://fake')
        cur = _FakeCursor(fetch_one=None)
        conn = _FakeConn(cur=cur)

        with patch('psycopg.connect', return_value=conn), patch.object(rb, 'run') as run_mock:
            rc = rb.cli(['missing-job', '886bf8b'])

        assert rc == 2
        run_mock.assert_not_called()
        # No commit — lookup failed before any writes.
        assert conn.commits == 0
        assert conn.rollbacks == 1
        assert conn.closed is True


class TestCliSnapshotMissing:
    def test_returns_4_when_pgbackrest_doesnt_have_snapshot(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv('CONTROL_PLANE_PG_DSN', 'postgresql://fake')
        cur = _FakeCursor(fetch_one=_job_row())
        conn = _FakeConn(cur=cur)

        with patch('psycopg.connect', return_value=conn), patch.object(
            rb,
            'run',
            return_value=rb.RollbackResult(
                job_id='job-uuid',
                snapshot_id='snap-pre-migration',
                status='snapshot_missing',
            ),
        ):
            rc = rb.cli(['job-uuid', '886bf8b'])

        assert rc == 4
        # Finalize did NOT run — no last_migrated_sha bump on missing snapshot.
        assert not any('UPDATE tenants' in c[0] for c in cur.executed)


class TestCliRestoreFailed:
    def test_returns_3(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv('CONTROL_PLANE_PG_DSN', 'postgresql://fake')
        cur = _FakeCursor(fetch_one=_job_row())
        conn = _FakeConn(cur=cur)

        with patch('psycopg.connect', return_value=conn), patch.object(
            rb,
            'run',
            return_value=rb.RollbackResult(
                job_id='job-uuid',
                snapshot_id='snap-pre-migration',
                status='restore_failed',
            ),
        ):
            rc = rb.cli(['job-uuid', '886bf8b'])

        assert rc == 3
        assert not any('UPDATE tenants' in c[0] for c in cur.executed)


class TestRollbackActorEnv:
    def test_rollback_actor_overrides_github_actor(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv('CONTROL_PLANE_PG_DSN', 'postgresql://fake')
        monkeypatch.setenv('GITHUB_ACTOR', 'gha')
        monkeypatch.setenv('ROLLBACK_ACTOR', 'security-lead')
        cur = _FakeCursor(fetch_one=_job_row())
        conn = _FakeConn(cur=cur)

        with patch('psycopg.connect', return_value=conn), patch.object(
            rb,
            'run',
            return_value=rb.RollbackResult(
                job_id='job-uuid',
                snapshot_id='snap-pre-migration',
                status='ok',
            ),
        ) as run_mock:
            rb.cli(['job-uuid', '886bf8b'])

        plan_arg = run_mock.call_args[0][0]
        assert plan_arg.actor == 'security-lead'
