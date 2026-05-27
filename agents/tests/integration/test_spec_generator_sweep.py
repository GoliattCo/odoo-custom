"""Integration test for spec_generator.core.sweep (PR3: 24h auto-confirm)."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

import pytest

from agents.config import Bindings, Config, RuntimeConfig
from agents.ports import Comment, Issue
from agents.spec_generator import core


@dataclass
class FakeIssues:
    comments_posted: list[dict[str, Any]] = field(default_factory=list)
    labels_added: list[tuple[int, str]] = field(default_factory=list)
    labels_removed: list[tuple[int, str]] = field(default_factory=list)

    def open_issue(self, *_a, **_kw):
        raise NotImplementedError

    def comment(self, issue: Issue, body: str) -> Comment:
        self.comments_posted.append({"issue": issue.number, "body": body})
        return Comment(id=len(self.comments_posted), body=body,
                       author="spec-generator-bot", issue_number=issue.number)

    def edit_comment(self, *_a, **_kw):
        pass

    def add_label(self, issue: Issue, label: str):
        self.labels_added.append((issue.number, label))

    def remove_label(self, issue: Issue, label: str):
        self.labels_removed.append((issue.number, label))

    def list_issues(self, **_kw):
        return []

    def search_similar(self, *_a, **_kw):
        return []


@dataclass
class FakeLogger:
    events: list[tuple[str, str, dict]] = field(default_factory=list)

    def _emit(self, lvl, msg, **f):
        self.events.append((lvl, msg, f))

    def info(self, msg, /, **f):
        self._emit("info", msg, **f)

    def warn(self, msg, /, **f):
        self._emit("warn", msg, **f)

    def error(self, msg, /, **f):
        self._emit("error", msg, **f)

    def debug(self, msg, /, **f):
        self._emit("debug", msg, **f)

    def bind(self, **_f):
        return self

    @contextmanager
    def span(self, name, /, **f):
        self._emit("info", f"{name}.start", **f)
        try:
            yield
        finally:
            self._emit("info", f"{name}.end", **f)


@dataclass
class FakeRuntime:
    issues: Any = None
    repo: Any = None
    llm: Any = None
    notifier: Any = None
    logger: Any = None
    config: Any = None


@pytest.fixture
def runtime() -> FakeRuntime:
    cfg = Config(
        runtime=RuntimeConfig(), bindings=Bindings(),
        extras={}, agents={"spec_generator": {}},
    )
    return FakeRuntime(
        issues=FakeIssues(), logger=FakeLogger(), config=cfg,
    )


def _cand(*, pr=901, issue=126, branch="agent/spec-126",
          spec_path="docs/superpowers/specs/foo-design.md",
          updated_at="2026-05-25T09:00:00+00:00",
          labels=("spec-drafted", "awaiting-reporter-confirm"),
          spec_body=""):
    return {
        "pr_number": pr, "issue_number": issue, "branch": branch,
        "spec_path": spec_path, "updated_at": updated_at,
        "labels": list(labels), "spec_body": spec_body,
    }


_NOW = "2026-05-27T09:00:00+00:00"  # 48h after the default updated_at


# ---------------------------------------------------------------------------

def test_sweep_confirms_silent_pr_past_24h(runtime: FakeRuntime) -> None:
    payload = {"now": _NOW, "candidates": [_cand()]}
    summary = core.sweep(runtime, payload)

    assert summary["confirmed"] == [901]
    assert summary["act"] is True
    assert (901, "intent-confirmed") in runtime.issues.labels_added
    assert (901, "awaiting-reporter-confirm") in runtime.issues.labels_removed
    # Close-out comment posted on the original issue (not the PR) so the
    # Slack intake bot relays it back into the originating thread.
    assert any(c["issue"] == 126 and "No further input" in c["body"]
               for c in runtime.issues.comments_posted)


def test_sweep_skips_pr_younger_than_24h(runtime: FakeRuntime) -> None:
    payload = {
        "now": _NOW,
        "candidates": [_cand(updated_at="2026-05-27T08:00:00+00:00")],  # 1h old
    }
    summary = core.sweep(runtime, payload)
    assert summary["confirmed"] == []
    assert summary["decisions"][0]["action"] == "skip"
    assert summary["decisions"][0]["reason"].startswith("too_young:")
    assert runtime.issues.labels_added == []


def test_sweep_skips_pr_with_needs_clarification_marker(runtime: FakeRuntime) -> None:
    payload = {"now": _NOW, "candidates": [_cand(
        spec_body="...\n[NEEDS CLARIFICATION] still waiting on tenant impact\n",
    )]}
    summary = core.sweep(runtime, payload)
    assert summary["confirmed"] == []
    assert summary["decisions"][0]["reason"] == "needs_clarification_marker"


def test_sweep_skips_already_confirmed_pr(runtime: FakeRuntime) -> None:
    payload = {"now": _NOW, "candidates": [_cand(
        labels=("spec-drafted", "intent-confirmed"),
    )]}
    summary = core.sweep(runtime, payload)
    assert summary["decisions"][0]["reason"] == "already_confirmed"
    assert runtime.issues.labels_added == []


def test_sweep_dry_run_emits_decisions_but_no_writes(runtime: FakeRuntime) -> None:
    payload = {"now": _NOW, "dry_run": True, "candidates": [_cand()]}
    summary = core.sweep(runtime, payload)
    assert summary["confirmed"] == []
    assert summary["decisions"][0]["action"] == "confirm"
    assert summary["act"] is False
    assert runtime.issues.labels_added == []


def test_sweep_in_shadow_mode_emits_decisions_only(runtime: FakeRuntime) -> None:
    runtime.config.agents["spec_generator"] = {"shadow_mode": True}
    payload = {"now": _NOW, "candidates": [_cand()]}
    summary = core.sweep(runtime, payload)
    assert summary["act"] is False
    assert summary["decisions"][0]["action"] == "confirm"
    assert runtime.issues.labels_added == []


def test_sweep_handles_missing_updated_at(runtime: FakeRuntime) -> None:
    payload = {"now": _NOW, "candidates": [_cand(updated_at="")]}
    summary = core.sweep(runtime, payload)
    assert summary["decisions"][0]["reason"] == "no_updated_at"


def test_sweep_multiple_candidates(runtime: FakeRuntime) -> None:
    payload = {
        "now": _NOW,
        "candidates": [
            _cand(pr=901, issue=126),
            _cand(pr=902, issue=127, updated_at="2026-05-27T08:00:00+00:00"),
            _cand(pr=903, issue=128,
                  labels=("spec-drafted", "intent-confirmed")),
        ],
    }
    summary = core.sweep(runtime, payload)
    assert summary["confirmed"] == [901]
    assert summary["total"] == 3
