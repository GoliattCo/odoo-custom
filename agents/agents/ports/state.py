"""StateStore port — persistent agent state.

Default adapter: SqliteStateStore (Fly volume / local file).
Future adapters: PostgresStateStore, RedisStateStore.

Holds three things the slack_intake agent needs to survive restarts:
1. The thread <-> issue link table (which Slack thread maps to which GH issue).
2. The Slack <-> GitHub user mapping.
3. A dedupe set for webhook deliveries (Slack event_id, GH X-GitHub-Delivery).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class ThreadIssueLink:
    slack_channel: str
    slack_thread_ts: str
    github_repo: str
    github_issue_number: int
    reporter_slack_id: str
    created_at: datetime
    last_relayed_comment_id: int | None = None
    intent_confirmed_at: datetime | None = None


class StateStore(Protocol):
    # ---- Thread <-> Issue ----

    def link_thread_to_issue(self, link: ThreadIssueLink) -> None:
        """Insert a new thread<->issue mapping. Idempotent on PK."""
        ...

    def get_link_by_thread(
        self, *, channel: str, thread_ts: str,
    ) -> ThreadIssueLink | None: ...

    def get_link_by_issue(
        self, *, repo: str, issue_number: int,
    ) -> ThreadIssueLink | None: ...

    def mark_intent_confirmed(
        self, *, channel: str, thread_ts: str, at: datetime,
    ) -> None: ...

    def update_last_relayed_comment(
        self, *, channel: str, thread_ts: str, comment_id: int,
    ) -> None: ...

    # ---- User mapping ----

    def map_user(
        self,
        *,
        slack_user_id: str,
        github_login: str,
        method: str = "manual",
    ) -> None: ...

    def lookup_github_login(self, *, slack_user_id: str) -> str | None: ...

    # ---- Dedupe ----

    def seen_event(self, *, key: str) -> bool:
        """Return True if `key` was seen before. Otherwise record it and return False.

        Implementations MAY age out entries past `ttl_hours`. The slack_intake
        agent's defaults are fine with 24h retention.
        """
        ...
