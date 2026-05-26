"""In-memory StateStore — tests only. Loses data on restart.

Bootstrap uses this when `bindings.state == "memory"`. Production should
always use `sqlite` (or a future Postgres adapter).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from ..ports import StateStore, ThreadIssueLink

_DEFAULT_DEDUPE_TTL_HOURS = 24


def _utcnow() -> datetime:
    return datetime.now(UTC)


class InMemoryStateStore:
    """Dict-backed StateStore. NOT for production."""

    def __init__(self, *, dedupe_ttl_hours: int = _DEFAULT_DEDUPE_TTL_HOURS) -> None:
        self._links_by_thread: dict[tuple[str, str], ThreadIssueLink] = {}
        self._links_by_issue: dict[tuple[str, int], ThreadIssueLink] = {}
        self._user_map: dict[str, str] = {}
        self._dedupe: dict[str, datetime] = {}
        self._ttl = timedelta(hours=dedupe_ttl_hours)

    def link_thread_to_issue(self, link: ThreadIssueLink) -> None:
        self._links_by_thread[(link.slack_channel, link.slack_thread_ts)] = link
        self._links_by_issue[(link.github_repo, link.github_issue_number)] = link

    def get_link_by_thread(
        self, *, channel: str, thread_ts: str,
    ) -> ThreadIssueLink | None:
        return self._links_by_thread.get((channel, thread_ts))

    def get_link_by_issue(
        self, *, repo: str, issue_number: int,
    ) -> ThreadIssueLink | None:
        return self._links_by_issue.get((repo, issue_number))

    def mark_intent_confirmed(
        self, *, channel: str, thread_ts: str, at: datetime,
    ) -> None:
        key = (channel, thread_ts)
        existing = self._links_by_thread.get(key)
        if existing is None:
            return
        from dataclasses import replace
        updated = replace(existing, intent_confirmed_at=at)
        self._links_by_thread[key] = updated
        self._links_by_issue[(existing.github_repo, existing.github_issue_number)] = updated

    def update_last_relayed_comment(
        self, *, channel: str, thread_ts: str, comment_id: int,
    ) -> None:
        key = (channel, thread_ts)
        existing = self._links_by_thread.get(key)
        if existing is None:
            return
        from dataclasses import replace
        updated = replace(existing, last_relayed_comment_id=comment_id)
        self._links_by_thread[key] = updated
        self._links_by_issue[(existing.github_repo, existing.github_issue_number)] = updated

    def map_user(
        self, *, slack_user_id: str, github_login: str, method: str = "manual",
    ) -> None:
        self._user_map[slack_user_id] = github_login

    def lookup_github_login(self, *, slack_user_id: str) -> str | None:
        return self._user_map.get(slack_user_id)

    def seen_event(self, *, key: str) -> bool:
        # Age out
        cutoff = _utcnow() - self._ttl
        self._dedupe = {k: v for k, v in self._dedupe.items() if v >= cutoff}
        if key in self._dedupe:
            return True
        self._dedupe[key] = _utcnow()
        return False


_ = StateStore  # Protocol check
