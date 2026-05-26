"""Port interfaces (Protocols / ABCs).

Agent core code depends on these and ONLY these. Adapters in
`agents.adapters` implement them; the bootstrap wires them at startup.

Port signatures are SemVer-stable across major versions. Breaking changes
require a major bump of the agents package.
"""

from .artifact_store import ArtifactStore
from .chat_ops import ChatOps, PostedMessage
from .compute_env import ComputeEnv, Deployment, Status
from .event_bus import Event, EventBus, Subscription
from .issue_tracker import Comment, Issue, IssueTracker
from .knowledge_base import KbChunk, KnowledgeBase
from .llm_provider import ChatResponse, LLMProvider, Message, Tool, Vector
from .logger import Logger
from .notifier import Notifier, Severity
from .repo import GitIdentity, PullRequest, Repo
from .secret_store import SecretStore
from .state import StateStore, ThreadIssueLink

__all__ = [
    # llm
    "LLMProvider", "Message", "ChatResponse", "Tool", "Vector",
    # repo
    "Repo", "PullRequest", "GitIdentity",
    # issues
    "IssueTracker", "Issue", "Comment",
    # notifier
    "Notifier", "Severity",
    # chat ops
    "ChatOps", "PostedMessage",
    # secrets
    "SecretStore",
    # artifacts
    "ArtifactStore",
    # compute
    "ComputeEnv", "Deployment", "Status",
    # kb
    "KnowledgeBase", "KbChunk",
    # events
    "EventBus", "Event", "Subscription",
    # state
    "StateStore", "ThreadIssueLink",
    # logger
    "Logger",
]
