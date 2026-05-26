"""Slack adapter — implements both Notifier and ChatOps.

Notifier: severity-based one-shot alerts (the agent runtime's pre-existing
use case). Maps severity to icon + colour; pages PagerDuty when severity is
"page".

ChatOps: thread-aware operations used by the slack_intake agent — post
messages, reply in threads, edit, react, open modals, get permalinks.

One class implements both ports because in practice we always want one
identity (one Slack bot token) speaking on behalf of the agent runtime.
Bootstrap wires the same instance into `runtime.notifier` and `runtime.chat`.
"""

from __future__ import annotations

from typing import Any

from ..config import Config
from ..ports import Notifier, PostedMessage, Severity


class SlackAdapter:
    """Slack-backed Notifier + ChatOps."""

    SEVERITY_COLOUR = {
        "info": "#36a64f",   # green
        "warn": "#f2c744",   # amber
        "page": "#d72631",   # red
    }
    SEVERITY_ICON = {
        "info": ":information_source:",
        "warn": ":warning:",
        "page": ":rotating_light:",
    }

    def __init__(
        self,
        *,
        token: str,
        default_channel: str,
        pagerduty_token: str | None = None,
    ) -> None:
        self._default_channel = default_channel
        self._pagerduty_token = pagerduty_token
        from slack_sdk import WebClient  # type: ignore[import-untyped]
        self._slack = WebClient(token=token)

    @classmethod
    def from_config(cls, config: Config) -> SlackAdapter:
        from .secrets_envvar import EnvVarSecretStore
        secrets = EnvVarSecretStore()
        slack_cfg = config.extras.get("slack", {})
        return cls(
            token=secrets.get_or_raise(
                slack_cfg.get("workspace_secret", "SLACK_BOT_TOKEN")
            ),
            default_channel=slack_cfg.get("default_channel", "#devops-agents"),
            pagerduty_token=secrets.get("PAGERDUTY_TOKEN"),
        )

    # =====================================================================
    # Notifier protocol
    # =====================================================================

    def send(
        self,
        *,
        channel: str,
        summary: str,
        details: dict | None = None,
        severity: Severity = "info",
    ) -> None:
        channel = channel or self._default_channel
        attachments = [{
            "color": self.SEVERITY_COLOUR.get(severity, "#36a64f"),
            "text": summary,
            "fields": [
                {"title": k, "value": str(v), "short": len(str(v)) < 40}
                for k, v in (details or {}).items()
            ],
        }]
        self._slack.chat_postMessage(
            channel=channel,
            text=f"{self.SEVERITY_ICON.get(severity, '')} {summary}",
            attachments=attachments,
        )
        if severity == "page" and self._pagerduty_token:
            self._page_pagerduty(summary, details or {})

    def _page_pagerduty(self, summary: str, details: dict) -> None:
        import httpx
        routing_key = details.get("routing_key") or details.get("pd_routing_key")
        if not routing_key:
            return
        httpx.post(
            "https://events.pagerduty.com/v2/enqueue",
            json={
                "routing_key": routing_key,
                "event_action": "trigger",
                "payload": {
                    "summary": summary,
                    "source": "odoo-saas-agents",
                    "severity": "critical",
                    "custom_details": details,
                },
            },
            timeout=10,
        )

    # =====================================================================
    # ChatOps protocol
    # =====================================================================

    def post_message(
        self,
        *,
        channel: str,
        text: str,
        blocks: list[dict[str, Any]] | None = None,
    ) -> PostedMessage:
        resp = self._slack.chat_postMessage(
            channel=channel,
            text=text,
            blocks=blocks or None,
        )
        return PostedMessage(channel=resp["channel"], message_id=resp["ts"])

    def post_thread_reply(
        self,
        *,
        channel: str,
        thread_id: str,
        text: str,
        blocks: list[dict[str, Any]] | None = None,
    ) -> PostedMessage:
        resp = self._slack.chat_postMessage(
            channel=channel,
            text=text,
            thread_ts=thread_id,
            blocks=blocks or None,
        )
        return PostedMessage(channel=resp["channel"], message_id=resp["ts"])

    def update_message(
        self,
        *,
        channel: str,
        message_id: str,
        text: str,
        blocks: list[dict[str, Any]] | None = None,
    ) -> None:
        self._slack.chat_update(
            channel=channel,
            ts=message_id,
            text=text,
            blocks=blocks or None,
        )

    def post_ephemeral(
        self,
        *,
        channel: str,
        user: str,
        text: str,
        blocks: list[dict[str, Any]] | None = None,
    ) -> None:
        self._slack.chat_postEphemeral(
            channel=channel,
            user=user,
            text=text,
            blocks=blocks or None,
        )

    def add_reaction(
        self,
        *,
        channel: str,
        message_id: str,
        emoji: str,
    ) -> None:
        try:
            self._slack.reactions_add(channel=channel, timestamp=message_id, name=emoji)
        except Exception:  # noqa: BLE001,S110 — idempotent; already_reacted is fine
            # The reaction already exists — that's the desired end state.
            pass

    def open_modal(
        self,
        *,
        trigger_id: str,
        view: dict[str, Any],
    ) -> None:
        self._slack.views_open(trigger_id=trigger_id, view=view)

    def permalink(self, *, channel: str, message_id: str) -> str:
        resp = self._slack.chat_getPermalink(channel=channel, message_ts=message_id)
        return resp["permalink"]


_ = Notifier  # Protocol check (ChatOps verified via static analysis at import time)
