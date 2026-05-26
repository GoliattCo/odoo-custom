"""ChatOps port — thread-aware chat-platform operations.

Distinct from Notifier (which is severity-based one-shot alerts). ChatOps is
for agents that own a multi-turn conversation on a chat platform — post
messages, reply in threads, edit, react, open modals.

Default adapter: SlackChatOpsAdapter (in agents.adapters.notifier_slack).
Future adapters: TeamsChatOpsAdapter, DiscordChatOpsAdapter.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class PostedMessage:
    """A message that has been posted to a chat platform."""
    channel: str
    message_id: str        # platform-specific (Slack: ts, Discord: snowflake)
    permalink: str | None = None


class ChatOps(Protocol):
    def post_message(
        self,
        *,
        channel: str,
        text: str,
        blocks: list[dict[str, Any]] | None = None,
    ) -> PostedMessage:
        """Post a top-level message in a channel or DM."""
        ...

    def post_thread_reply(
        self,
        *,
        channel: str,
        thread_id: str,
        text: str,
        blocks: list[dict[str, Any]] | None = None,
    ) -> PostedMessage:
        """Reply in a thread started by message `thread_id`."""
        ...

    def update_message(
        self,
        *,
        channel: str,
        message_id: str,
        text: str,
        blocks: list[dict[str, Any]] | None = None,
    ) -> None:
        """Edit an existing message in place."""
        ...

    def post_ephemeral(
        self,
        *,
        channel: str,
        user: str,
        text: str,
        blocks: list[dict[str, Any]] | None = None,
    ) -> None:
        """Send a message only `user` sees. Not all platforms support this."""
        ...

    def add_reaction(
        self,
        *,
        channel: str,
        message_id: str,
        emoji: str,
    ) -> None:
        """Add an emoji reaction. `emoji` is the bare name without colons."""
        ...

    def open_modal(
        self,
        *,
        trigger_id: str,
        view: dict[str, Any],
    ) -> None:
        """Open a modal in response to a slash-command / button trigger."""
        ...

    def permalink(self, *, channel: str, message_id: str) -> str:
        """Return a stable URL for the message."""
        ...
