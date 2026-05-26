"""Contract test for GitHubWebhookEventBus signature verification + dispatch."""

from __future__ import annotations

import hashlib
import hmac
import json

from agents.adapters.events_github_webhook import GitHubWebhookEventBus

WEBHOOK_SECRET = "test_gh_secret"  # noqa: S105 — test fixture, not a real secret


def _sign(body: bytes) -> str:
    return "sha256=" + hmac.new(
        WEBHOOK_SECRET.encode("utf-8"), body, hashlib.sha256,
    ).hexdigest()


def _bus() -> GitHubWebhookEventBus:
    return GitHubWebhookEventBus(webhook_secret=WEBHOOK_SECRET)


def test_valid_signature_routes_to_handler() -> None:
    bus = _bus()
    seen: list[dict] = []
    bus.subscribe("github.issue_comment.created", lambda e: seen.append(e.payload))

    payload = {
        "action": "created",
        "issue": {"number": 42, "labels": [{"name": "source:slack"}]},
        "comment": {"id": 1, "body": "hi", "user": {"login": "spec-generator-bot"}},
        "repository": {"full_name": "org/repo"},
    }
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "x-hub-signature-256": _sign(body),
        "x-github-event": "issue_comment",
        "x-github-delivery": "deliv-1",
    }
    result = bus.dispatch(headers=headers, body=body)
    assert result.status == 200
    assert len(seen) == 1
    assert seen[0]["delivery_id"] == "deliv-1"
    assert seen[0]["issue"]["number"] == 42


def test_invalid_signature_returns_401() -> None:
    bus = _bus()
    body = json.dumps({"action": "created"}).encode("utf-8")
    headers = {"x-hub-signature-256": "sha256=deadbeef"}
    result = bus.dispatch(headers=headers, body=body)
    assert result.status == 401


def test_missing_signature_returns_401() -> None:
    bus = _bus()
    body = b"{}"
    result = bus.dispatch(headers={}, body=body)
    assert result.status == 401


def test_unrelated_event_still_routes() -> None:
    """Adapter is generic; routing keeps non-issue_comment events too."""
    bus = _bus()
    seen: list[dict] = []
    bus.subscribe("github.push", lambda e: seen.append(e.payload))

    body = json.dumps({"ref": "refs/heads/main"}).encode("utf-8")
    headers = {
        "x-hub-signature-256": _sign(body),
        "x-github-event": "push",
        "x-github-delivery": "deliv-2",
    }
    result = bus.dispatch(headers=headers, body=body)
    assert result.status == 200
    assert len(seen) == 1
