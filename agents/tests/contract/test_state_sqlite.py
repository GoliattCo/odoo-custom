"""Contract test for SqliteStateStore."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from agents.adapters.state_sqlite import SqliteStateStore
from agents.ports import ThreadIssueLink


@pytest.fixture
def store(tmp_path: Path) -> SqliteStateStore:
    return SqliteStateStore(path=tmp_path / "test.db", dedupe_ttl_hours=24)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _link(**overrides) -> ThreadIssueLink:
    defaults = {
        "slack_channel": "C1",
        "slack_thread_ts": "1700000000.000001",
        "github_repo": "org/repo",
        "github_issue_number": 42,
        "reporter_slack_id": "U1",
        "created_at": _utcnow(),
    }
    defaults.update(overrides)
    return ThreadIssueLink(**defaults)


def test_round_trip_link(store: SqliteStateStore) -> None:
    link = _link()
    store.link_thread_to_issue(link)
    by_thread = store.get_link_by_thread(channel="C1", thread_ts="1700000000.000001")
    assert by_thread is not None
    assert by_thread.github_issue_number == 42

    by_issue = store.get_link_by_issue(repo="org/repo", issue_number=42)
    assert by_issue is not None
    assert by_issue.slack_channel == "C1"


def test_link_replace_is_idempotent(store: SqliteStateStore) -> None:
    store.link_thread_to_issue(_link())
    # Insert again — should not raise.
    store.link_thread_to_issue(_link(reporter_slack_id="U2"))
    link = store.get_link_by_thread(channel="C1", thread_ts="1700000000.000001")
    assert link is not None
    assert link.reporter_slack_id == "U2"


def test_mark_intent_confirmed(store: SqliteStateStore) -> None:
    store.link_thread_to_issue(_link())
    when = _utcnow()
    store.mark_intent_confirmed(channel="C1", thread_ts="1700000000.000001", at=when)
    link = store.get_link_by_thread(channel="C1", thread_ts="1700000000.000001")
    assert link is not None
    assert link.intent_confirmed_at is not None


def test_update_last_relayed(store: SqliteStateStore) -> None:
    store.link_thread_to_issue(_link())
    store.update_last_relayed_comment(
        channel="C1", thread_ts="1700000000.000001", comment_id=999,
    )
    link = store.get_link_by_thread(channel="C1", thread_ts="1700000000.000001")
    assert link is not None
    assert link.last_relayed_comment_id == 999


def test_user_mapping_round_trip(store: SqliteStateStore) -> None:
    store.map_user(slack_user_id="U1", github_login="alice", method="email-match")
    assert store.lookup_github_login(slack_user_id="U1") == "alice"
    assert store.lookup_github_login(slack_user_id="U2") is None


def test_user_mapping_replaces(store: SqliteStateStore) -> None:
    store.map_user(slack_user_id="U1", github_login="alice")
    store.map_user(slack_user_id="U1", github_login="alice-renamed")
    assert store.lookup_github_login(slack_user_id="U1") == "alice-renamed"


def test_dedupe_first_call_false(store: SqliteStateStore) -> None:
    assert store.seen_event(key="evt:1") is False


def test_dedupe_second_call_true(store: SqliteStateStore) -> None:
    store.seen_event(key="evt:1")
    assert store.seen_event(key="evt:1") is True


def test_dedupe_aged_out(tmp_path: Path) -> None:
    store = SqliteStateStore(path=tmp_path / "ttl.db", dedupe_ttl_hours=0)
    # ttl_hours=0 means everything ages out immediately on next call.
    store.seen_event(key="evt:1")
    # Different key, so it triggers the DELETE; then evt:1 is gone.
    store.seen_event(key="evt:2")
    assert store.seen_event(key="evt:1") is False
