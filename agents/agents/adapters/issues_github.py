"""GitHub IssueTracker adapter — promotes the bootstrap stub to a real impl.

Uses PyGithub (already a project dep via repo-github optional). Falls back
to no-op `search_similar` until pgvector wiring lands (Phase 9+).
"""

from __future__ import annotations

from typing import Any

from ..config import Config
from ..ports import Comment, Issue, IssueTracker


class GitHubIssuesAdapter:
    """IssueTracker backed by GitHub Issues REST API via PyGithub."""

    def __init__(
        self,
        *,
        org: str,
        repo: str,
        token: str,
    ) -> None:
        from github import Github  # type: ignore[import-untyped]
        self._org = org
        self._repo_name = repo
        self._gh = Github(token)
        self._repo = self._gh.get_repo(f"{org}/{repo}")

    @classmethod
    def from_config(cls, config: Config) -> GitHubIssuesAdapter:
        from .secrets_envvar import EnvVarSecretStore
        secrets = EnvVarSecretStore()
        gh_cfg: dict[str, Any] = config.extras.get("github", {})
        return cls(
            org=gh_cfg.get("org", ""),
            repo=gh_cfg.get("repo", ""),
            token=secrets.get_or_raise(gh_cfg.get("token_secret", "GITHUB_TOKEN")),
        )

    # ---- IssueTracker protocol ----

    def open_issue(
        self,
        *,
        title: str,
        body: str,
        labels: tuple[str, ...] = (),
    ) -> Issue:
        gh_issue = self._repo.create_issue(
            title=title,
            body=body,
            labels=list(labels),
        )
        return self._to_issue(gh_issue)

    def comment(self, issue: Issue, body: str) -> Comment:
        gh_issue = self._repo.get_issue(number=issue.number)
        gh_comment = gh_issue.create_comment(body)
        return Comment(
            id=gh_comment.id,
            body=gh_comment.body or "",
            author=gh_comment.user.login if gh_comment.user else "unknown",
            issue_number=issue.number,
        )

    def edit_comment(self, comment: Comment, body: str) -> None:
        # Find the comment via its issue + ID. PyGithub doesn't expose a
        # direct "get comment by ID" on Repo, so we re-fetch via issue.
        gh_issue = self._repo.get_issue(number=comment.issue_number)
        for gh_comment in gh_issue.get_comments():
            if gh_comment.id == comment.id:
                gh_comment.edit(body)
                return

    def add_label(self, issue: Issue, label: str) -> None:
        gh_issue = self._repo.get_issue(number=issue.number)
        gh_issue.add_to_labels(label)

    def remove_label(self, issue: Issue, label: str) -> None:
        gh_issue = self._repo.get_issue(number=issue.number)
        try:
            gh_issue.remove_from_labels(label)
        except Exception:  # noqa: BLE001,S110 — idempotent; PyGithub raises generic
            # The label is already gone — that's the desired end state.
            pass

    def list_issues(
        self,
        *,
        labels: tuple[str, ...] | None = None,
        state: str = "open",
    ) -> list[Issue]:
        kwargs: dict[str, Any] = {"state": state}
        if labels:
            kwargs["labels"] = list(labels)
        return [self._to_issue(i) for i in self._repo.get_issues(**kwargs)]

    def search_similar(self, text: str, *, limit: int = 5) -> list[Issue]:
        """Embedding-based search; defers to pgvector once that adapter lands."""
        # Until pgvector is wired, fall back to a GitHub-side full-text search.
        query = f"repo:{self._org}/{self._repo_name} {text}"
        results = self._gh.search_issues(query=query)
        out: list[Issue] = []
        for i, item in enumerate(results):
            if i >= limit:
                break
            out.append(self._to_issue(item))
        return out

    # ---- helpers ----

    def _to_issue(self, gh_issue: Any) -> Issue:
        return Issue(
            number=gh_issue.number,
            title=gh_issue.title,
            body=gh_issue.body or "",
            labels=tuple(label.name for label in gh_issue.labels),
            state=gh_issue.state,
            author=gh_issue.user.login if gh_issue.user else "unknown",
            url=gh_issue.html_url,
        )


_ = IssueTracker  # Protocol check
