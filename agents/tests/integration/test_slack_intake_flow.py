"""Integration test for the slack_intake agent core.

Exercises Path A through D without touching real Slack or GitHub. Uses
fakes for the ChatOps, IssueTracker, and Notifier ports and a real
SqliteStateStore over a tmp file.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from agents.adapters.state_sqlite import SqliteStateStore
from agents.config import Bindings, Config, RuntimeConfig
from agents.ports import Issue, PostedMessage
from agents.slack_intake import core as intake

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

@dataclass
class FakeChatOps:
    posted: list[dict[str, Any]] = field(default_factory=list)
    ephemerals: list[dict[str, Any]] = field(default_factory=list)
    threaded: list[dict[str, Any]] = field(default_factory=list)
    updates: list[dict[str, Any]] = field(default_factory=list)
    reactions: list[dict[str, Any]] = field(default_factory=list)
    opened_modals: list[dict[str, Any]] = field(default_factory=list)
    next_ts: int = 1700000000

    def _ts(self) -> str:
        self.next_ts += 1
        return f"{self.next_ts}.000001"

    def post_message(self, *, channel: str, text: str, blocks=None) -> PostedMessage:
        ts = self._ts()
        self.posted.append({"channel": channel, "ts": ts, "text": text, "blocks": blocks})
        return PostedMessage(channel=channel, message_id=ts)

    def post_thread_reply(
        self, *, channel: str, thread_id: str, text: str, blocks=None,
    ) -> PostedMessage:
        ts = self._ts()
        self.threaded.append(
            {"channel": channel, "thread_id": thread_id, "text": text, "blocks": blocks, "ts": ts}
        )
        return PostedMessage(channel=channel, message_id=ts)

    def update_message(self, *, channel: str, message_id: str, text: str, blocks=None) -> None:
        self.updates.append(
            {"channel": channel, "message_id": message_id, "text": text, "blocks": blocks}
        )

    def post_ephemeral(self, *, channel: str, user: str, text: str, blocks=None) -> None:
        self.ephemerals.append({"channel": channel, "user": user, "text": text})

    def add_reaction(self, *, channel: str, message_id: str, emoji: str) -> None:
        self.reactions.append({"channel": channel, "message_id": message_id, "emoji": emoji})

    def open_modal(self, *, trigger_id: str, view: dict) -> None:
        self.opened_modals.append({"trigger_id": trigger_id, "view": view})

    def permalink(self, *, channel: str, message_id: str) -> str:
        return f"https://slack.example/{channel}/{message_id}"


@dataclass
class FakeIssues:
    next_number: int = 100
    issues_created: list[dict[str, Any]] = field(default_factory=list)
    comments_posted: list[dict[str, Any]] = field(default_factory=list)

    def open_issue(self, *, title: str, body: str, labels: tuple[str, ...] = ()):
        n = self.next_number
        self.next_number += 1
        self.issues_created.append(
            {"number": n, "title": title, "body": body, "labels": list(labels)}
        )
        return Issue(
            number=n, title=title, body=body, labels=labels,
            state="open", author="bot",
            url=f"https://github.example/org/repo/issues/{n}",
        )

    def comment(self, issue, body):
        self.comments_posted.append({"issue": issue.number, "body": body})
        from agents.ports import Comment
        return Comment(id=len(self.comments_posted), body=body,
                       author="bot", issue_number=issue.number)


@dataclass
class FakeLogger:
    events: list[tuple[str, str, dict]] = field(default_factory=list)

    def _emit(self, level: str, msg: str, **fields: Any) -> None:
        self.events.append((level, msg, fields))

    def info(self, msg: str, /, **fields: Any) -> None:
        self._emit("info", msg, **fields)

    def warn(self, msg: str, /, **fields: Any) -> None:
        self._emit("warn", msg, **fields)

    def error(self, msg: str, /, **fields: Any) -> None:
        self._emit("error", msg, **fields)

    def debug(self, msg: str, /, **fields: Any) -> None:
        self._emit("debug", msg, **fields)

    def bind(self, **fields: Any):
        return self  # for test purposes a single logger is fine

    from contextlib import contextmanager

    @contextmanager
    def span(self, name: str, /, **fields: Any):  # type: ignore[no-untyped-def]
        self._emit("info", f"{name}.start", **fields)
        try:
            yield
        finally:
            self._emit("info", f"{name}.end", **fields)


# ---------------------------------------------------------------------------
# Runtime fixture
# ---------------------------------------------------------------------------

@dataclass
class FakeRuntime:
    """Mimics the bootstrap.Runtime dataclass enough for the agent core."""
    issues: Any
    chat: Any
    state: Any
    logger: Any
    config: Any
    events: Any = None        # not used in these tests


@pytest.fixture
def runtime(tmp_path: Path) -> FakeRuntime:
    state = SqliteStateStore(path=tmp_path / "state.db", dedupe_ttl_hours=24)
    cfg = Config(
        runtime=RuntimeConfig(),
        bindings=Bindings(),
        extras={"github": {"org": "org", "repo": "repo"}},
        agents={
            "slack_intake": {
                "allowed_channels": ["C1"],
                "relay_authors": ["spec-generator-bot"],
                "sensitive_patterns": [r"(?i)password"],
            },
        },
    )
    return FakeRuntime(
        issues=FakeIssues(),
        chat=FakeChatOps(),
        state=state,
        logger=FakeLogger(),
        config=cfg,
    )


# ---------------------------------------------------------------------------
# Path A — slash command + modal
# ---------------------------------------------------------------------------

def test_slash_command_opens_modal_in_allowed_channel(runtime: FakeRuntime) -> None:
    intake.on_slash_command(runtime, {
        "command": "/intake",
        "channel_id": "C1",
        "user_id": "U1",
        "trigger_id": "trig.1",
    })
    assert len(runtime.chat.opened_modals) == 1
    assert runtime.chat.opened_modals[0]["trigger_id"] == "trig.1"


def test_slash_command_blocked_in_unlisted_channel(runtime: FakeRuntime) -> None:
    intake.on_slash_command(runtime, {
        "command": "/intake",
        "channel_id": "C-not-allowed",
        "user_id": "U1",
        "trigger_id": "trig.1",
    })
    assert runtime.chat.opened_modals == []
    assert len(runtime.chat.ephemerals) == 1
    assert "not enabled" in runtime.chat.ephemerals[0]["text"]


def test_modal_submission_creates_issue_and_thread(runtime: FakeRuntime) -> None:
    payload = _modal_submission_payload(
        title="Search broken", description="No results when filter applied",
        kind="bug", severity="high",
    )
    result = intake.on_modal_submitted(runtime, payload)
    assert result is None  # modal closes cleanly

    # Issue was created with correct labels
    assert len(runtime.issues.issues_created) == 1
    created = runtime.issues.issues_created[0]
    assert created["title"] == "Search broken"
    assert "bug" in created["labels"]
    assert "severity:high" in created["labels"]
    assert "source:slack" in created["labels"]

    # Confirmation message posted in the originating channel
    assert len(runtime.chat.posted) == 1
    assert "Filed" in runtime.chat.posted[0]["text"]
    assert f"#{created['number']}" in runtime.chat.posted[0]["text"]

    # And the thread link is in state
    posted = runtime.chat.posted[0]
    link = runtime.state.get_link_by_thread(channel=posted["channel"], thread_ts=posted["ts"])
    assert link is not None
    assert link.github_issue_number == created["number"]
    assert link.reporter_slack_id == "U1"


def test_sensitive_topic_is_refused(runtime: FakeRuntime) -> None:
    payload = _modal_submission_payload(
        title="My account",
        description="What's my password? Please send it.",
        kind="bug", severity="low",
    )
    result = intake.on_modal_submitted(runtime, payload)
    assert result is not None
    assert result.get("response_action") == "errors"
    assert "errors" in result
    assert runtime.issues.issues_created == []
    assert len(runtime.chat.ephemerals) == 1


# ---------------------------------------------------------------------------
# Path B — GitHub comment relays into Slack thread
# ---------------------------------------------------------------------------

def test_spec_generator_comment_relays_to_thread(runtime: FakeRuntime) -> None:
    # Set up a tracked thread first
    _seed_link(runtime, channel="C1", thread_ts="t.1", issue_number=100)

    intake.on_github_issue_comment(runtime, _gh_comment_payload(
        issue_number=100,
        comment_body="What addon is this in?",
        author="spec-generator-bot",
        delivery_id="d-1",
    ))

    assert len(runtime.chat.threaded) == 1
    relay = runtime.chat.threaded[0]
    assert relay["channel"] == "C1"
    assert relay["thread_id"] == "t.1"


def test_relay_normalises_bot_login_suffix(runtime: FakeRuntime) -> None:
    """GitHub Apps author comments as "<slug>[bot]"; the relay allowlist holds
    the bare slug, so the suffix must be normalised or the relay silently
    drops every spec-generator comment (the prod gap behind issue #126)."""
    _seed_link(runtime, channel="C1", thread_ts="t.1", issue_number=100)

    intake.on_github_issue_comment(runtime, _gh_comment_payload(
        issue_number=100,
        comment_body="I've drafted a design spec for this issue.",
        author="spec-generator-bot[bot]",
        delivery_id="d-bot-suffix",
    ))

    assert len(runtime.chat.threaded) == 1
    assert runtime.chat.threaded[0]["thread_id"] == "t.1"


def test_shadow_mode_blocks_github_to_slack_relay(runtime: FakeRuntime) -> None:
    """Phase B: when shadow_mode=true, no relay even if everything else matches."""
    runtime.config.agents["slack_intake"]["shadow_mode"] = True
    _seed_link(runtime, channel="C1", thread_ts="t.1", issue_number=100)
    intake.on_github_issue_comment(runtime, _gh_comment_payload(
        issue_number=100,
        comment_body="What addon is this in?",
        author="spec-generator-bot",
        delivery_id="d-shadow",
    ))
    assert runtime.chat.threaded == []


def test_relay_skipped_after_intent_confirmed(runtime: FakeRuntime) -> None:
    _seed_link(runtime, channel="C1", thread_ts="t.1", issue_number=100)
    runtime.state.mark_intent_confirmed(
        channel="C1", thread_ts="t.1", at=datetime.now(UTC),
    )
    intake.on_github_issue_comment(runtime, _gh_comment_payload(
        issue_number=100,
        comment_body="late comment",
        author="spec-generator-bot",
        delivery_id="d-2",
    ))
    assert runtime.chat.threaded == []


def test_relay_ignores_unrecognised_author(runtime: FakeRuntime) -> None:
    _seed_link(runtime, channel="C1", thread_ts="t.1", issue_number=100)
    intake.on_github_issue_comment(runtime, _gh_comment_payload(
        issue_number=100,
        comment_body="random user reply",
        author="some-random-user",
        delivery_id="d-3",
    ))
    assert runtime.chat.threaded == []


def test_relay_deduplicates_on_delivery_id(runtime: FakeRuntime) -> None:
    _seed_link(runtime, channel="C1", thread_ts="t.1", issue_number=100)
    payload = _gh_comment_payload(
        issue_number=100, comment_body="question", author="spec-generator-bot",
        delivery_id="d-dupe",
    )
    intake.on_github_issue_comment(runtime, payload)
    intake.on_github_issue_comment(runtime, payload)
    assert len(runtime.chat.threaded) == 1


# ---------------------------------------------------------------------------
# Path C — Slack thread message relays to GitHub
# ---------------------------------------------------------------------------

def test_slack_reply_relays_to_github_comment(runtime: FakeRuntime) -> None:
    _seed_link(runtime, channel="C1", thread_ts="t.1", issue_number=100,
               reporter_slack_id="U1")
    runtime.state.map_user(slack_user_id="U1", github_login="alice")

    intake.on_slack_message(runtime, {
        "event_id": "Ev-1",
        "channel": "C1",
        "thread_ts": "t.1",
        "user": "U1",
        "ts": "t.2",
        "text": "It happens on saas_tenant_gate",
    })

    assert len(runtime.issues.comments_posted) == 1
    comment = runtime.issues.comments_posted[0]
    assert comment["issue"] == 100
    assert "@alice" in comment["body"]
    assert "saas_tenant_gate" in comment["body"]

    # Delivery receipt reaction
    assert len(runtime.chat.reactions) == 1
    assert runtime.chat.reactions[0]["emoji"] == "eyes"


def test_slack_reply_skipped_after_intent_confirmed(runtime: FakeRuntime) -> None:
    _seed_link(runtime, channel="C1", thread_ts="t.1", issue_number=100)
    runtime.state.mark_intent_confirmed(
        channel="C1", thread_ts="t.1", at=datetime.now(UTC),
    )
    intake.on_slack_message(runtime, {
        "event_id": "Ev-2",
        "channel": "C1", "thread_ts": "t.1", "user": "U1", "ts": "t.3",
        "text": "any thoughts?",
    })
    assert runtime.issues.comments_posted == []


def test_bot_messages_ignored(runtime: FakeRuntime) -> None:
    _seed_link(runtime, channel="C1", thread_ts="t.1", issue_number=100)
    intake.on_slack_message(runtime, {
        "event_id": "Ev-bot",
        "channel": "C1", "thread_ts": "t.1",
        "bot_id": "B123", "text": "I am a bot",
    })
    assert runtime.issues.comments_posted == []


def test_top_level_messages_ignored(runtime: FakeRuntime) -> None:
    intake.on_slack_message(runtime, {
        "event_id": "Ev-top",
        "channel": "C1", "user": "U1",
        "text": "hello (not in a thread)",
    })
    assert runtime.issues.comments_posted == []


# ---------------------------------------------------------------------------
# Path D — confirm button
# ---------------------------------------------------------------------------

def test_confirm_button_posts_slash_confirm_and_marks_state(runtime: FakeRuntime) -> None:
    _seed_link(runtime, channel="C1", thread_ts="t.1", issue_number=100,
               reporter_slack_id="U1")
    import json
    intake.on_block_action(runtime, {
        "user": {"id": "U1"},
        "actions": [{
            "action_id": "intake_confirm",
            "value": json.dumps({"channel": "C1", "thread_ts": "t.1"}),
        }],
        "message": {"ts": "card.1"},
    })

    # /confirm comment was posted to GitHub
    assert len(runtime.issues.comments_posted) == 1
    assert runtime.issues.comments_posted[0]["body"] == "/confirm"

    # State updated
    link = runtime.state.get_link_by_thread(channel="C1", thread_ts="t.1")
    assert link is not None
    assert link.intent_confirmed_at is not None

    # Card was edited to show confirmation
    assert len(runtime.chat.updates) == 1
    assert "Intent confirmed" in runtime.chat.updates[0]["text"]


def test_confirm_button_only_reporter_can_use(runtime: FakeRuntime) -> None:
    _seed_link(runtime, channel="C1", thread_ts="t.1", issue_number=100,
               reporter_slack_id="U1")
    import json
    intake.on_block_action(runtime, {
        "user": {"id": "U-NOT-REPORTER"},
        "actions": [{
            "action_id": "intake_confirm",
            "value": json.dumps({"channel": "C1", "thread_ts": "t.1"}),
        }],
        "message": {"ts": "card.1"},
    })
    assert runtime.issues.comments_posted == []
    assert len(runtime.chat.ephemerals) == 1
    assert "Only the original reporter" in runtime.chat.ephemerals[0]["text"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _modal_submission_payload(
    *, title: str, description: str, kind: str, severity: str, addon: str | None = None,
) -> dict[str, Any]:
    import json
    state_values: dict[str, Any] = {
        "title": {"title_input": {"value": title}},
        "description": {"description_input": {"value": description}},
        "kind": {"kind_select": {"selected_option": {"value": kind}}},
        "severity": {"severity_select": {"selected_option": {"value": severity}}},
    }
    if addon:
        state_values["addon"] = {"addon_select": {"selected_option": {"value": addon}}}
    else:
        state_values["addon"] = {"addon_select": {}}
    return {
        "user": {"id": "U1", "username": "reporter"},
        "view": {
            "callback_id": "intake_submit",
            "state": {"values": state_values},
            "private_metadata": json.dumps({"origin_channel": "C1"}),
        },
    }


def _gh_comment_payload(
    *,
    issue_number: int,
    comment_body: str,
    author: str,
    delivery_id: str,
) -> dict[str, Any]:
    return {
        "delivery_id": delivery_id,
        "issue": {
            "number": issue_number,
            "html_url": f"https://github.example/org/repo/issues/{issue_number}",
            "labels": [{"name": "source:slack"}, {"name": "bug"}],
        },
        "comment": {
            "id": 555 + issue_number,
            "body": comment_body,
            "user": {"login": author},
        },
        "repository": {"full_name": "org/repo"},
    }


def _seed_link(
    runtime: FakeRuntime,
    *,
    channel: str,
    thread_ts: str,
    issue_number: int,
    reporter_slack_id: str = "U1",
) -> None:
    from agents.ports import ThreadIssueLink
    runtime.state.link_thread_to_issue(ThreadIssueLink(
        slack_channel=channel,
        slack_thread_ts=thread_ts,
        github_repo="org/repo",
        github_issue_number=issue_number,
        reporter_slack_id=reporter_slack_id,
        created_at=datetime.now(UTC),
    ))
