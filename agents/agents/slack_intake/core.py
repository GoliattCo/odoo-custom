"""Slack Intake agent core — Slack <-> GitHub bridge for Spec Generator phase.

Pure-Python; depends only on port interfaces. The FastAPI service in
`agents.services.slack_intake_http` wires inbound Slack and GitHub webhooks
through their respective EventBus adapters into the handlers below.

Four code paths (lettered to match the design doc):
    Path A  /intake → modal → GitHub issue created
    Path B  Spec Generator GH comment → Slack thread reply
    Path C  Slack thread reply → GitHub issue comment
    Path D  "Confirm intent" button → /confirm comment on GH issue
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..ports import Issue

# Labels applied to every issue this agent files.
_INTAKE_LABEL = "source:slack"

# The Spec-Generator agent (or human CODEOWNERS) — only their comments get
# relayed back to Slack. Configurable via agents.slack_intake.relay_authors.
_DEFAULT_RELAY_AUTHORS = ("spec-generator-bot",)

# A small sensitive-topic regex — config can override with a richer set.
_DEFAULT_SENSITIVE_PATTERNS = (
    r"(?i)\b(password|api[\s_-]?key|secret|private[\s_-]?key)\b",
    r"(?i)\b(credit[\s_-]?card|cvv|ssn|social[\s_-]?security)\b",
    r"(?i)\b(billing|invoice|refund|chargeback)\b",
    r"(?i)\b(security|breach|cve|0day)\b",
    r"(?i)\b(legal|gdpr|dmca|lawsuit)\b",
)

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"


# =========================================================================
# Entry point invoked by CLI (`agents run slack-intake`) — starts the HTTP service.
# =========================================================================

def run(runtime, payload: dict) -> None:
    """Start the FastAPI service so Slack and GitHub webhooks can be received."""
    log = runtime.logger.bind(agent="slack_intake")
    log.info("slack_intake.start", payload=payload)

    # Lazy import — fastapi/uvicorn are optional install extras.
    from ..services import slack_intake_http

    # Wire handlers BEFORE starting the HTTP listener so we never lose an
    # in-flight webhook.
    _register_handlers(runtime)
    slack_intake_http.serve(
        runtime=runtime,
        host=payload.get("host", "0.0.0.0"),  # noqa: S104 — Fly proxy fronts this
        port=int(payload.get("port", 8080)),
    )


# =========================================================================
# Handler registration — subscribes to the EventBus
# =========================================================================

def _register_handlers(runtime) -> None:
    events = runtime.events
    events.subscribe("slack.slash_command",
                     lambda e: on_slash_command(runtime, e.payload))
    events.subscribe("slack.modal_submitted",
                     lambda e: on_modal_submitted(runtime, e.payload))
    events.subscribe("slack.block_action",
                     lambda e: on_block_action(runtime, e.payload))
    events.subscribe("slack.message",
                     lambda e: on_slack_message(runtime, e.payload))
    # GitHub side — wired through a separate EventBus on the same agent; the
    # HTTP service registers this independently because the runtime's
    # `events` port is bound to the Slack EventBus.
    runtime.logger.info("slack_intake.handlers_registered")


# =========================================================================
# Path A — /intake slash command opens the modal
# =========================================================================

def on_slash_command(runtime, payload: dict) -> None:
    """Reply to `/intake` by opening a modal collecting the intake fields."""
    log = runtime.logger.bind(agent="slack_intake", path="A")
    command = payload.get("command", "")
    if command != "/intake":
        log.debug("slack_intake.ignored_command", command=command)
        return

    channel_id = payload.get("channel_id", "")
    if not _channel_allowed(runtime, channel_id):
        log.info("slack_intake.channel_not_allowed", channel=channel_id)
        runtime.chat.post_ephemeral(
            channel=channel_id,
            user=payload.get("user_id", ""),
            text=(
                ":lock: `/intake` is not enabled in this channel yet. "
                "Ask an admin to add it to `slack_intake.allowed_channels`."
            ),
        )
        return

    view = _render_modal(runtime, channel_id=channel_id)
    runtime.chat.open_modal(trigger_id=payload["trigger_id"], view=view)
    log.info("slack_intake.modal_opened", user=payload.get("user_id"))


def _render_modal(runtime, *, channel_id: str) -> dict[str, Any]:
    template = json.loads((_TEMPLATES_DIR / "intake_modal.json").read_text())
    # Carry the originating channel through as private_metadata so we can
    # post the confirmation reply in the right place after submission.
    template["private_metadata"] = json.dumps({"origin_channel": channel_id})
    # Populate addon options from custom-addons/ if available.
    addon_options = _enumerate_addons(runtime)
    if addon_options:
        for block in template.get("blocks", []):
            if block.get("block_id") == "addon" and "element" in block:
                block["element"]["options"] = addon_options
    return template


def _enumerate_addons(runtime) -> list[dict[str, Any]]:
    """Return a list of Slack option dicts populated from the addon set, capped at 100."""
    cfg = (runtime.config.agents or {}).get("slack_intake", {})
    addons: list[str] = cfg.get("addon_choices", [])
    if not addons:
        return []
    # Slack hard-caps select option count at 100.
    return [{"text": {"type": "plain_text", "text": a}, "value": a}
            for a in addons[:100]]


# =========================================================================
# Path A (cont.) — modal submission creates the GitHub issue
# =========================================================================

def on_modal_submitted(runtime, payload: dict) -> dict[str, Any] | None:
    """Create the GitHub issue and post the confirmation thread root in Slack."""
    log = runtime.logger.bind(agent="slack_intake", path="A")
    view = payload.get("view", {})
    if view.get("callback_id") != "intake_submit":
        return None

    values = _extract_modal_values(view)
    user = payload.get("user", {})
    slack_user_id = user.get("id", "")
    slack_user_name = user.get("username") or user.get("name", "unknown")
    private_meta = json.loads(view.get("private_metadata") or "{}")
    origin_channel = private_meta.get("origin_channel", "")

    if _is_sensitive(runtime, values["description"]):
        log.info("slack_intake.sensitive_blocked", user=slack_user_id)
        runtime.chat.post_ephemeral(
            channel=origin_channel,
            user=slack_user_id,
            text=(
                ":no_entry_sign: This looks like a sensitive topic "
                "(billing / security / legal). Please email support@ "
                "instead — `/intake` is for product bugs and feature requests."
            ),
        )
        # Return a Slack `response_action: errors` so the modal shows the
        # rejection inline.
        return {
            "response_action": "errors",
            "errors": {"description": (
                "Sensitive topics (billing, security, legal) should not be "
                "filed via /intake — email support@."
            )},
        }

    kind = values["kind"]                # "bug" or "feature"
    severity = values["severity"]        # "low" | "medium" | "high"
    addon = values.get("addon")          # optional
    title = values["title"].strip()
    description = values["description"].strip()

    labels = [
        "bug" if kind == "bug" else "feature-request",
        f"severity:{severity}",
        _INTAKE_LABEL,
    ]
    if addon:
        labels.append(f"addon:{addon}")

    body = _format_issue_body(
        description=description,
        slack_user_name=slack_user_name,
        slack_user_id=slack_user_id,
        origin_channel=origin_channel,
        kind=kind,
        severity=severity,
        addon=addon,
    )

    with log.span("slack_intake.create_issue", kind=kind, severity=severity):
        issue: Issue = runtime.issues.open_issue(
            title=title, body=body, labels=tuple(labels),
        )

    # Post the thread root in Slack — its ts is the join key for everything else.
    confirm_text = (
        f":white_check_mark: Filed <{issue.url}|#{issue.number}> "
        f"({kind} · severity {severity}). Reply in this thread to answer "
        f"the Spec Generator's questions when they arrive."
    )
    posted = runtime.chat.post_message(channel=origin_channel, text=confirm_text)
    runtime.state.link_thread_to_issue(_make_link(
        channel=posted.channel,
        thread_ts=posted.message_id,
        repo=_repo_full_name(runtime),
        issue_number=issue.number,
        reporter_slack_id=slack_user_id,
    ))
    log.info(
        "slack_intake.issue_created",
        issue=issue.number, channel=posted.channel, thread_ts=posted.message_id,
    )
    return None  # Slack closes the modal


# =========================================================================
# Path B — GitHub issue comment relays into the Slack thread
# =========================================================================

def on_github_issue_comment(runtime, payload: dict) -> None:
    """Forward a Spec-Generator comment back into the originating Slack thread."""
    log = runtime.logger.bind(agent="slack_intake", path="B")

    # Phase-B shadow mode: do not relay GH -> Slack. Issues still get filed
    # (Path A is unaffected) so the team can sanity-check issue body quality
    # without a noisy round trip.
    if _shadow_mode(runtime):
        log.info("slack_intake.shadow_mode_skip_relay")
        return

    delivery_id = payload.get("delivery_id") or payload.get("X-GitHub-Delivery", "")
    if delivery_id and runtime.state.seen_event(key=f"gh:{delivery_id}"):
        log.debug("slack_intake.duplicate_delivery", delivery_id=delivery_id)
        return

    issue = payload.get("issue") or {}
    comment = payload.get("comment") or {}
    repo = (payload.get("repository") or {}).get("full_name", "")
    issue_number = issue.get("number")
    if not issue_number:
        return

    labels = {label.get("name") for label in issue.get("labels", []) if isinstance(label, dict)}
    if _INTAKE_LABEL not in labels:
        return  # Not a Slack-originated issue; ignore.

    link = runtime.state.get_link_by_issue(repo=repo, issue_number=issue_number)
    if link is None:
        log.warn("slack_intake.unknown_issue", repo=repo, issue=issue_number)
        return
    if link.intent_confirmed_at is not None:
        log.info("slack_intake.relay_skipped_post_confirm", issue=issue_number)
        return  # Impl Agent owns the conversation from here.

    author = (comment.get("user") or {}).get("login", "")
    relay_authors = tuple(
        (runtime.config.agents or {})
        .get("slack_intake", {})
        .get("relay_authors", _DEFAULT_RELAY_AUTHORS)
    )
    if author not in relay_authors:
        log.debug("slack_intake.author_not_relayed", author=author)
        return

    if comment.get("id") and link.last_relayed_comment_id == comment["id"]:
        return  # already relayed

    blocks = _render_relay_card(
        author=author,
        body=_mask_pii(runtime, comment.get("body", "")),
        issue_url=issue.get("html_url", ""),
        issue_number=issue_number,
        channel=link.slack_channel,
        thread_ts=link.slack_thread_ts,
    )
    runtime.chat.post_thread_reply(
        channel=link.slack_channel,
        thread_id=link.slack_thread_ts,
        text=f"New comment from @{author} on #{issue_number}",
        blocks=blocks,
    )
    if comment.get("id"):
        runtime.state.update_last_relayed_comment(
            channel=link.slack_channel,
            thread_ts=link.slack_thread_ts,
            comment_id=comment["id"],
        )
    log.info("slack_intake.relayed_to_slack", issue=issue_number, author=author)


# =========================================================================
# Path C — Slack thread message relays to GitHub as an issue comment
# =========================================================================

def on_slack_message(runtime, payload: dict) -> None:
    """Forward a thread reply on a tracked thread back to GitHub as a comment."""
    log = runtime.logger.bind(agent="slack_intake", path="C")
    event_id = payload.get("event_id", "")
    if event_id and runtime.state.seen_event(key=f"slack:{event_id}"):
        return

    # Slack delivers many message subtypes; only treat top-level user
    # replies in threads. Subtype-bearing events (bot_message, channel_join,
    # etc.) and our own bot's posts are ignored.
    if payload.get("bot_id") or payload.get("subtype"):
        return
    thread_ts = payload.get("thread_ts")
    if not thread_ts:
        return  # Not a thread reply; nothing to relay.

    channel = payload.get("channel", "")
    link = runtime.state.get_link_by_thread(channel=channel, thread_ts=thread_ts)
    if link is None:
        return
    if link.intent_confirmed_at is not None:
        # Reporter has confirmed intent; the implementation-agent stage owns
        # the conversation from here. Don't echo back.
        return

    text = payload.get("text", "").strip()
    if not text:
        return

    slack_user_id = payload.get("user", "")
    gh_login = runtime.state.lookup_github_login(slack_user_id=slack_user_id)
    attribution = f"@{gh_login}" if gh_login else f"Slack user `{slack_user_id}`"

    body = (
        f"> _Relayed from Slack thread (originating reporter: {attribution})_\n\n"
        f"{_mask_pii(runtime, text)}"
    )

    issue = Issue(
        number=link.github_issue_number, title="", body="", labels=(),
        state="open", author="", url="",
    )
    runtime.issues.comment(issue, body)
    log.info("slack_intake.relayed_to_github",
             issue=link.github_issue_number, slack_user=slack_user_id)

    # Delivery receipt
    posted_ts = payload.get("ts")
    if posted_ts:
        runtime.chat.add_reaction(channel=channel, message_id=posted_ts, emoji="eyes")


# =========================================================================
# Path D — "Confirm intent" button posts /confirm on the GH issue
# =========================================================================

def on_block_action(runtime, payload: dict) -> None:
    """React to the Confirm-intent button on a relayed card."""
    log = runtime.logger.bind(agent="slack_intake", path="D")
    actions = payload.get("actions") or []
    if not actions:
        return
    action = actions[0]
    if action.get("action_id") != "intake_confirm":
        return

    # The button's `value` carries the link key we need.
    raw = action.get("value", "")
    try:
        meta = json.loads(raw)
    except json.JSONDecodeError:
        return
    channel = meta.get("channel", "")
    thread_ts = meta.get("thread_ts", "")

    link = runtime.state.get_link_by_thread(channel=channel, thread_ts=thread_ts)
    if link is None:
        return

    clicker = (payload.get("user") or {}).get("id", "")
    if clicker != link.reporter_slack_id:
        runtime.chat.post_ephemeral(
            channel=channel, user=clicker,
            text=":lock: Only the original reporter can confirm intent on this issue.",
        )
        return

    issue = Issue(
        number=link.github_issue_number, title="", body="", labels=(),
        state="open", author="", url="",
    )
    runtime.issues.comment(issue, "/confirm")
    now = datetime.now(UTC)
    runtime.state.mark_intent_confirmed(channel=channel, thread_ts=thread_ts, at=now)

    # Edit the original card to show the confirmation.
    message = payload.get("message") or {}
    message_id = message.get("ts")
    if message_id:
        runtime.chat.update_message(
            channel=channel,
            message_id=message_id,
            text=f"✅ Intent confirmed at {now.isoformat()}",
            blocks=_render_confirmed_card(
                issue_number=link.github_issue_number,
                confirmed_at=now,
                clicker=clicker,
            ),
        )
    log.info("slack_intake.intent_confirmed",
             issue=link.github_issue_number, clicker=clicker)


# =========================================================================
# Helpers
# =========================================================================

def iterate(runtime, payload: dict) -> None:
    """No-op for now — slack_intake has no iteration phase distinct from `run`."""
    runtime.logger.info("slack_intake.iterate.noop", payload=payload)


def _shadow_mode(runtime) -> bool:
    """Phase B flag — when True, the bot files issues but does not relay.

    Sourced from `agents.slack_intake.shadow_mode` in config, overridable
    via the AGENTS_AGENTS_SLACK_INTAKE_SHADOW_MODE env var (set by Fly).
    """
    cfg = (runtime.config.agents or {}).get("slack_intake", {})
    value = cfg.get("shadow_mode", False)
    if isinstance(value, str):
        return value.lower() in ("1", "true", "yes")
    return bool(value)


def _channel_allowed(runtime, channel_id: str) -> bool:
    cfg = (runtime.config.agents or {}).get("slack_intake", {})
    allowed = cfg.get("allowed_channels", []) or []
    if not allowed:
        # An empty list means "no channels allowed yet" — fail closed.
        return False
    return "*" in allowed or channel_id in allowed


def _is_sensitive(runtime, text: str) -> bool:
    import re
    cfg = (runtime.config.agents or {}).get("slack_intake", {})
    patterns = cfg.get("sensitive_patterns") or _DEFAULT_SENSITIVE_PATTERNS
    return any(re.search(p, text) for p in patterns)


def _mask_pii(runtime, text: str) -> str:
    """Cheap deny-list mask. Phase B can upgrade to the 3-layer chain."""
    import re
    redacted = text
    # Emails
    redacted = re.sub(r"[\w.+-]+@[\w-]+\.[\w.-]+", "<email>", redacted)
    # Phone-like sequences (very rough — full mask comes in Phase B)
    redacted = re.sub(r"\b\+?\d[\d\s().-]{7,}\d\b", "<phone>", redacted)
    return redacted


def _format_issue_body(
    *,
    description: str,
    slack_user_name: str,
    slack_user_id: str,
    origin_channel: str,
    kind: str,
    severity: str,
    addon: str | None,
) -> str:
    parts = [
        description,
        "",
        "---",
        f"Filed via Slack `/intake` by @{slack_user_name} (`{slack_user_id}`)",
        f"From channel `{origin_channel}` · kind={kind} · severity={severity}",
    ]
    if addon:
        parts.append(f"Addon: `{addon}`")
    return "\n".join(parts)


def _make_link(
    *,
    channel: str,
    thread_ts: str,
    repo: str,
    issue_number: int,
    reporter_slack_id: str,
):
    from ..ports import ThreadIssueLink
    return ThreadIssueLink(
        slack_channel=channel,
        slack_thread_ts=thread_ts,
        github_repo=repo,
        github_issue_number=issue_number,
        reporter_slack_id=reporter_slack_id,
        created_at=datetime.now(UTC),
    )


def _repo_full_name(runtime) -> str:
    gh_cfg = runtime.config.extras.get("github", {})
    return f"{gh_cfg.get('org', '')}/{gh_cfg.get('repo', '')}"


def _extract_modal_values(view: dict[str, Any]) -> dict[str, Any]:
    """Pull out the form values from a view_submission payload."""
    state = view.get("state", {}).get("values", {})
    def pick(block_id: str, action_id: str) -> Any:
        action = state.get(block_id, {}).get(action_id, {})
        if "value" in action:
            return action["value"]
        if "selected_option" in action and action["selected_option"]:
            return action["selected_option"]["value"]
        if "selected_options" in action:
            opts = action["selected_options"] or []
            return opts[0]["value"] if opts else None
        return None
    return {
        "title": pick("title", "title_input") or "",
        "description": pick("description", "description_input") or "",
        "kind": pick("kind", "kind_select") or "bug",
        "severity": pick("severity", "severity_select") or "medium",
        "addon": pick("addon", "addon_select"),
    }


def _render_relay_card(
    *,
    author: str,
    body: str,
    issue_url: str,
    issue_number: int,
    channel: str,
    thread_ts: str,
) -> list[dict[str, Any]]:
    template = json.loads((_TEMPLATES_DIR / "relay_card.json").read_text())
    action_value_json = json.dumps({"channel": channel, "thread_ts": thread_ts})
    # Escape the JSON for safe embedding inside another JSON string literal.
    action_value_escaped = (
        action_value_json.replace("\\", "\\\\").replace("\"", "\\\"")
    )
    rendered: list[dict[str, Any]] = []
    for block in template:
        text = json.dumps(block)
        text = text.replace("{{author}}", _json_escape(author))
        text = text.replace("{{body}}", _json_escape(body))
        text = text.replace("{{issue_url}}", _json_escape(issue_url))
        text = text.replace("{{issue_number}}", str(issue_number))
        text = text.replace("{{action_value_json}}", action_value_escaped)
        rendered.append(json.loads(text))
    return rendered


def _json_escape(s: str) -> str:
    """Escape a string for safe substitution inside an already-JSON-encoded payload."""
    return (
        s.replace("\\", "\\\\")
         .replace("\"", "\\\"")
         .replace("\n", "\\n")
         .replace("\r", "\\r")
         .replace("\t", "\\t")
    )


def _render_confirmed_card(
    *, issue_number: int, confirmed_at: datetime, clicker: str,
) -> list[dict[str, Any]]:
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f":white_check_mark: *Intent confirmed* for #{issue_number} "
                    f"by <@{clicker}> at `{confirmed_at.isoformat()}`. "
                    f"Implementation Agent will pick up from here."
                ),
            },
        }
    ]
