"""Contract test for SlackWebhookEventBus signature verification + dispatch."""

from __future__ import annotations

import hashlib
import hmac
import json
import time

from agents.adapters.events_slack_webhook import SlackWebhookEventBus

SIGNING_SECRET = "test_signing_secret"  # noqa: S105 — test fixture, not a real secret


def _sign(body: bytes, ts: int) -> dict[str, str]:
    base = b"v0:" + str(ts).encode("ascii") + b":" + body
    sig = "v0=" + hmac.new(
        SIGNING_SECRET.encode("utf-8"), base, hashlib.sha256,
    ).hexdigest()
    return {
        "x-slack-signature": sig,
        "x-slack-request-timestamp": str(ts),
    }


def _bus() -> SlackWebhookEventBus:
    return SlackWebhookEventBus(signing_secret=SIGNING_SECRET)


def test_signature_verified_for_fresh_request() -> None:
    body = b"command=%2Fintake&user_id=U1"
    ts = int(time.time())
    bus = _bus()
    assert bus.verify_signature(headers=_sign(body, ts), body=body, now=ts) is True


def test_signature_rejected_for_stale_request() -> None:
    body = b"command=%2Fintake"
    ts = int(time.time()) - 1000   # 16 minutes old; past the 5-min cutoff
    bus = _bus()
    assert bus.verify_signature(headers=_sign(body, ts), body=body) is False


def test_signature_rejected_for_tampered_body() -> None:
    body = b"command=%2Fintake"
    ts = int(time.time())
    headers = _sign(body, ts)
    tampered = b"command=%2Fevil"
    bus = _bus()
    assert bus.verify_signature(headers=headers, body=tampered, now=ts) is False


def test_signature_rejected_when_header_missing() -> None:
    body = b"command=%2Fintake"
    assert _bus().verify_signature(headers={}, body=body) is False


def test_url_verification_handshake() -> None:
    body = json.dumps({"type": "url_verification", "challenge": "abc123"}).encode()
    ts = int(time.time())
    bus = _bus()
    result = bus.dispatch(
        headers={**_sign(body, ts), "content-type": "application/json"},
        body=body, now=ts,
    )
    assert result.status == 200
    assert result.body == "abc123"


def test_slash_command_publishes_event() -> None:
    bus = _bus()
    seen: list[dict] = []
    bus.subscribe("slack.slash_command", lambda e: seen.append(e.payload))

    body = b"command=%2Fintake&user_id=U1&trigger_id=trig.42&channel_id=C1"
    ts = int(time.time())
    headers = {
        **_sign(body, ts),
        "content-type": "application/x-www-form-urlencoded",
    }
    result = bus.dispatch(headers=headers, body=body, now=ts)
    assert result.status == 200
    assert len(seen) == 1
    assert seen[0]["command"] == "/intake"
    assert seen[0]["user_id"] == "U1"


def test_interactivity_modal_submitted() -> None:
    bus = _bus()
    received: list[dict] = []
    bus.subscribe("slack.modal_submitted", lambda e: received.append(e.payload))

    inner = {"type": "view_submission", "view": {"callback_id": "intake_submit"}}
    body = ("payload=" + json.dumps(inner)).encode("utf-8")
    # urllib quoting note: the test's form parser handles bare JSON fine.
    ts = int(time.time())
    headers = {
        **_sign(body, ts),
        "content-type": "application/x-www-form-urlencoded",
    }
    result = bus.dispatch(headers=headers, body=body, now=ts)
    assert result.status == 200
    assert len(received) == 1
    assert received[0]["view"]["callback_id"] == "intake_submit"


def test_event_subscription_publishes_inner_event() -> None:
    bus = _bus()
    captured: list[dict] = []
    bus.subscribe("slack.message", lambda e: captured.append(e.payload))

    inner = {
        "type": "event_callback",
        "event_id": "Ev123",
        "event": {"type": "message", "text": "hello", "user": "U1", "channel": "C1"},
    }
    body = json.dumps(inner).encode("utf-8")
    ts = int(time.time())
    headers = {**_sign(body, ts), "content-type": "application/json"}
    result = bus.dispatch(headers=headers, body=body, now=ts)
    assert result.status == 200
    assert len(captured) == 1
    assert captured[0]["text"] == "hello"
    assert captured[0]["event_id"] == "Ev123"


def test_invalid_signature_returns_401() -> None:
    body = b"command=%2Fintake"
    ts = int(time.time())
    headers = {
        "x-slack-signature": "v0=deadbeef",
        "x-slack-request-timestamp": str(ts),
    }
    bus = _bus()
    result = bus.dispatch(headers=headers, body=body, now=ts)
    assert result.status == 401
