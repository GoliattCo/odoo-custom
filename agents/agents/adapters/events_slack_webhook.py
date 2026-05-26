"""Slack EventBus adapter — receives Slack webhooks.

Implements EventBus + a `dispatch()` entry point the HTTP service calls per
inbound request. Verifies signatures (Slack v0 HMAC), checks freshness,
parses the three request shapes Slack uses (slash command url-encoded,
event subscription JSON, interactivity JSON), and routes them through the
subscribed handlers.

Event types this adapter emits:
- `slack.slash_command`      — `/intake` invoked
- `slack.modal_submitted`    — modal callback fired
- `slack.block_action`       — button / select clicked
- `slack.message`            — message posted in a channel the bot reads
- `slack.url_verification`   — Slack's one-time URL handshake
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ..config import Config
from ..ports import Event, EventBus, Subscription

_MAX_AGE_SECONDS = 300       # Slack signing-secret docs: reject anything older than 5 min


@dataclass(frozen=True)
class DispatchResult:
    """Returned by `dispatch()`. The HTTP service uses `body` for the response."""
    status: int
    body: str = ""
    content_type: str = "text/plain"


class SlackWebhookEventBus:
    """EventBus that receives Slack webhooks."""

    def __init__(
        self,
        *,
        signing_secret: str,
        max_age_seconds: int = _MAX_AGE_SECONDS,
    ) -> None:
        self._signing_secret = signing_secret.encode("utf-8")
        self._max_age = max_age_seconds
        self._subs: dict[str, list[Callable[[Event], Any]]] = {}
        self._next_sub_id = 0

    @classmethod
    def from_config(cls, config: Config) -> SlackWebhookEventBus:
        from .secrets_envvar import EnvVarSecretStore
        secrets = EnvVarSecretStore()
        cfg: dict[str, Any] = config.extras.get("slack", {})
        return cls(
            signing_secret=secrets.get_or_raise(
                cfg.get("signing_secret_name", "SLACK_SIGNING_SECRET")
            ),
        )

    # ---- EventBus protocol ----

    def subscribe(
        self,
        event_type: str,
        handler: Callable[[Event], Any],
    ) -> Subscription:
        self._next_sub_id += 1
        sub_id = f"slack-sub-{self._next_sub_id}"
        self._subs.setdefault(event_type, []).append(handler)
        return Subscription(id=sub_id, event_type=event_type)

    def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        event = Event(type=event_type, actor="slack", payload=payload)
        for handler in self._subs.get(event_type, []):
            handler(event)

    # ---- HTTP entry point ----

    def dispatch(
        self,
        *,
        headers: dict[str, str],
        body: bytes,
        now: float | None = None,
    ) -> DispatchResult:
        """Verify, parse, and route a single inbound Slack request.

        Returns a DispatchResult the HTTP service translates to a response.
        """
        if not self.verify_signature(headers=headers, body=body, now=now):
            return DispatchResult(status=401, body="invalid signature")

        # Slack URL-handshake (only fires once per app install)
        try:
            decoded_text = body.decode("utf-8")
        except UnicodeDecodeError:
            return DispatchResult(status=400, body="invalid utf-8")

        # JSON Events API + interactivity carry application/json; slash
        # commands carry application/x-www-form-urlencoded.
        content_type = headers.get("content-type", "").lower()
        if "application/json" in content_type:
            try:
                payload = json.loads(decoded_text)
            except json.JSONDecodeError:
                return DispatchResult(status=400, body="invalid json")
            return self._dispatch_json(payload)

        # url-encoded slash command or legacy interactivity
        form = dict(urllib.parse.parse_qsl(decoded_text))
        if "payload" in form:
            # Modal submit / button click arrives url-encoded with a JSON payload
            try:
                payload = json.loads(form["payload"])
            except json.JSONDecodeError:
                return DispatchResult(status=400, body="invalid interactivity payload")
            return self._dispatch_interactivity(payload)
        if "command" in form:
            return self._dispatch_slash_command(form)
        return DispatchResult(status=400, body="unrecognised slack request shape")

    # ---- signature verification ----

    def verify_signature(
        self, *, headers: dict[str, str], body: bytes, now: float | None = None,
    ) -> bool:
        """Slack v0 HMAC. Reject if missing, malformed, stale, or mismatched."""
        sig = headers.get("x-slack-signature") or headers.get("X-Slack-Signature")
        ts = headers.get("x-slack-request-timestamp") or headers.get(
            "X-Slack-Request-Timestamp"
        )
        if not sig or not ts:
            return False
        try:
            ts_int = int(ts)
        except ValueError:
            return False
        now = now if now is not None else time.time()
        if abs(now - ts_int) > self._max_age:
            return False
        basestring = b"v0:" + ts.encode("ascii") + b":" + body
        expected = "v0=" + hmac.new(
            self._signing_secret, basestring, hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, sig)

    # ---- per-shape routing ----

    def _dispatch_json(self, payload: dict[str, Any]) -> DispatchResult:
        kind = payload.get("type")
        if kind == "url_verification":
            # Slack sends one of these on every Event-Subscription URL
            # change. Respond with the challenge token verbatim.
            challenge = payload.get("challenge", "")
            return DispatchResult(status=200, body=str(challenge))
        if kind == "event_callback":
            inner = payload.get("event") or {}
            inner_type = inner.get("type", "unknown")
            # Slack delivers retries with the same event_id — record it.
            event_id = payload.get("event_id", "")
            self.publish(
                f"slack.{inner_type}",
                {"event_id": event_id, **inner},
            )
            return DispatchResult(status=200, body="ok")
        # Future: app_uninstalled etc.
        return DispatchResult(status=200, body="ok")

    def _dispatch_interactivity(self, payload: dict[str, Any]) -> DispatchResult:
        kind = payload.get("type", "")
        if kind == "view_submission":
            self.publish("slack.modal_submitted", payload)
            # Empty 200 body = close modal; "response_action: errors" handled
            # by the handler if it wants to.
            return DispatchResult(status=200, body="", content_type="application/json")
        if kind == "block_actions":
            self.publish("slack.block_action", payload)
            return DispatchResult(status=200, body="ok")
        if kind == "view_closed":
            self.publish("slack.modal_closed", payload)
            return DispatchResult(status=200, body="ok")
        return DispatchResult(status=200, body="ok")

    def _dispatch_slash_command(self, form: dict[str, str]) -> DispatchResult:
        self.publish("slack.slash_command", form)
        # The handler may have written to a response queue; for slash
        # commands we acknowledge with 200 + empty body within Slack's 3s
        # budget. Modal opening is done asynchronously via response_url
        # or via chat_ops.open_modal.
        return DispatchResult(status=200, body="", content_type="application/json")


_ = EventBus  # Protocol check
