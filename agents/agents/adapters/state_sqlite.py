"""SQLite-backed StateStore — the default for the slack_intake agent.

Schema lives in `_SCHEMA` and is applied on first connect. Three tables:
- `thread_issue` — Slack thread <-> GitHub issue mapping
- `user_mapping` — Slack user_id <-> GitHub login
- `dedupe` — webhook delivery IDs we've already processed

Persists to a single file. On Fly, the file lives on the mounted volume
at `/data/slack_intake.db` so it survives machine restarts.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from ..config import Config
from ..ports import StateStore, ThreadIssueLink

_SCHEMA = """
CREATE TABLE IF NOT EXISTS thread_issue (
    slack_channel       TEXT NOT NULL,
    slack_thread_ts     TEXT NOT NULL,
    github_repo         TEXT NOT NULL,
    github_issue_number INTEGER NOT NULL,
    reporter_slack_id   TEXT NOT NULL,
    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_relayed_comment_id INTEGER,
    intent_confirmed_at TIMESTAMP,
    PRIMARY KEY (slack_channel, slack_thread_ts)
);

CREATE INDEX IF NOT EXISTS idx_thread_issue_gh
    ON thread_issue (github_repo, github_issue_number);

CREATE TABLE IF NOT EXISTS user_mapping (
    slack_user_id  TEXT PRIMARY KEY,
    github_login   TEXT NOT NULL,
    linked_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    linked_method  TEXT NOT NULL DEFAULT 'manual'
);

CREATE TABLE IF NOT EXISTS dedupe (
    key      TEXT PRIMARY KEY,
    seen_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

_DEFAULT_DEDUPE_TTL_HOURS = 24


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _parse_dt(value: str | None) -> datetime | None:
    if value is None:
        return None
    # SQLite stores TIMESTAMP as ISO 8601 string; assume UTC.
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


class SqliteStateStore:
    """StateStore adapter using a single SQLite file."""

    def __init__(
        self,
        *,
        path: str | Path,
        dedupe_ttl_hours: int = _DEFAULT_DEDUPE_TTL_HOURS,
    ) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._dedupe_ttl_hours = dedupe_ttl_hours
        with self._connect() as conn:
            conn.executescript(_SCHEMA)
            conn.commit()

    @classmethod
    def from_config(cls, config: Config) -> SqliteStateStore:
        cfg: dict[str, Any] = config.extras.get("state_sqlite", {})
        return cls(
            path=cfg.get("path", "/data/slack_intake.db"),
            dedupe_ttl_hours=cfg.get("dedupe_ttl_hours", _DEFAULT_DEDUPE_TTL_HOURS),
        )

    @contextmanager
    def _connect(self) -> Any:
        conn = sqlite3.connect(self._path, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
        finally:
            conn.close()

    # ---- Thread <-> Issue ----

    def link_thread_to_issue(self, link: ThreadIssueLink) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO thread_issue (
                    slack_channel, slack_thread_ts, github_repo,
                    github_issue_number, reporter_slack_id, created_at,
                    last_relayed_comment_id, intent_confirmed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    link.slack_channel, link.slack_thread_ts, link.github_repo,
                    link.github_issue_number, link.reporter_slack_id,
                    link.created_at.isoformat(),
                    link.last_relayed_comment_id,
                    link.intent_confirmed_at.isoformat() if link.intent_confirmed_at else None,
                ),
            )

    def get_link_by_thread(
        self, *, channel: str, thread_ts: str,
    ) -> ThreadIssueLink | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM thread_issue WHERE slack_channel = ? AND slack_thread_ts = ?",
                (channel, thread_ts),
            ).fetchone()
        return self._row_to_link(row)

    def get_link_by_issue(
        self, *, repo: str, issue_number: int,
    ) -> ThreadIssueLink | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM thread_issue WHERE github_repo = ? AND github_issue_number = ?",
                (repo, issue_number),
            ).fetchone()
        return self._row_to_link(row)

    def mark_intent_confirmed(
        self, *, channel: str, thread_ts: str, at: datetime,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE thread_issue SET intent_confirmed_at = ? "
                "WHERE slack_channel = ? AND slack_thread_ts = ?",
                (at.isoformat(), channel, thread_ts),
            )

    def update_last_relayed_comment(
        self, *, channel: str, thread_ts: str, comment_id: int,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE thread_issue SET last_relayed_comment_id = ? "
                "WHERE slack_channel = ? AND slack_thread_ts = ?",
                (comment_id, channel, thread_ts),
            )

    @staticmethod
    def _row_to_link(row: sqlite3.Row | None) -> ThreadIssueLink | None:
        if row is None:
            return None
        return ThreadIssueLink(
            slack_channel=row["slack_channel"],
            slack_thread_ts=row["slack_thread_ts"],
            github_repo=row["github_repo"],
            github_issue_number=row["github_issue_number"],
            reporter_slack_id=row["reporter_slack_id"],
            created_at=_parse_dt(row["created_at"]) or _utcnow(),
            last_relayed_comment_id=row["last_relayed_comment_id"],
            intent_confirmed_at=_parse_dt(row["intent_confirmed_at"]),
        )

    # ---- User mapping ----

    def map_user(
        self,
        *,
        slack_user_id: str,
        github_login: str,
        method: str = "manual",
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO user_mapping
                    (slack_user_id, github_login, linked_at, linked_method)
                VALUES (?, ?, ?, ?)
                """,
                (slack_user_id, github_login, _utcnow().isoformat(), method),
            )

    def lookup_github_login(self, *, slack_user_id: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT github_login FROM user_mapping WHERE slack_user_id = ?",
                (slack_user_id,),
            ).fetchone()
        return row["github_login"] if row else None

    # ---- Dedupe ----

    def seen_event(self, *, key: str) -> bool:
        with self._connect() as conn:
            # Age out old entries opportunistically (cheap on small tables).
            cutoff = (_utcnow() - timedelta(hours=self._dedupe_ttl_hours)).isoformat()
            conn.execute("DELETE FROM dedupe WHERE seen_at < ?", (cutoff,))
            try:
                conn.execute(
                    "INSERT INTO dedupe (key, seen_at) VALUES (?, ?)",
                    (key, _utcnow().isoformat()),
                )
                return False
            except sqlite3.IntegrityError:
                return True


_ = StateStore  # Protocol check
