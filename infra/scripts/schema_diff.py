#!/usr/bin/env python3
"""Schema diff — Odoo model field additions/removals between two git refs.

Used by `.github/workflows/ci.yml::schema-diff`: when a PR touches files
under `custom-addons/*/models/`, this script walks each changed file at
BASE_SHA and HEAD_SHA, extracts the `models.Model` class definitions +
their `fields.<Type>(...)` declarations, and prints a markdown table
of additions / removals per `_name`. The CI step pipes the output to
`gh pr comment` so reviewers see a precise field-level changelog on the
PR.

Scope-limited on purpose:
  - Field additions (`+`) and removals (`−`) only. Type changes (e.g.
    `Char` → `Text`) and metadata edits (`string=`, `default=`) are
    noisy and not the primary signal — surfaced by the standard `git
    diff` viewer instead.
  - Only `<name> = fields.<Type>(...)` assignments are recognized.
    Computed-field shorthand (`_compute_foo` etc.) and `_inherits`
    extensions are intentionally out of scope; reviewers spot those
    in the diff.

Usage (driven by CI):
    BASE_SHA=<base> HEAD_SHA=<head> ./schema_diff.py
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys


def _git_show(ref: str, path: str) -> str | None:
    """Return `git show <ref>:<path>`, or `None` if the path doesn't exist
    at that ref (new files have no `BASE_SHA` content)."""
    proc = subprocess.run(
        ["git", "show", f"{ref}:{path}"],
        capture_output=True, text=True, check=False,
    )
    return proc.stdout if proc.returncode == 0 else None


def _extract_models(source: str) -> dict[str, dict[str, str]]:
    """Parse Python source, return ``{model_name: {field_name: field_type}}``.

    Recognizes top-level `class X(models.Model):` bodies and within them:
      - `_name = 'foo.bar'` — explicit model name.
      - `_inherit = 'foo.bar'` (classical inheritance) — falls back when
        no `_name` is set so an extension class surfaces its parent model
        (e.g. `event.event` for `class ClubEvent(models.Model): _inherit
        = 'event.event'`).
      - `<field> = fields.<Type>(...)` — the field's declared name + the
        unqualified `<Type>` token.

    Model-name resolution order: ``_name`` → ``_inherit`` (string form) →
    first entry of ``_inherit`` (list form) → class name. Matches Odoo's
    loader behaviour closely enough for diff-summary purposes.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {}
    models: dict[str, dict[str, str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        name_explicit: str | None = None
        inherit_fallback: str | None = None
        fields_map: dict[str, str] = {}
        for stmt in node.body:
            if not isinstance(stmt, ast.Assign) or len(stmt.targets) != 1:
                continue
            target = stmt.targets[0]
            if not isinstance(target, ast.Name):
                continue
            value = stmt.value
            # _name = 'foo.bar'
            if target.id == "_name" and isinstance(value, ast.Constant):
                name_explicit = str(value.value)
                continue
            # _inherit = 'foo.bar' OR _inherit = ['foo.bar', 'baz.qux']
            if target.id == "_inherit":
                if isinstance(value, ast.Constant):
                    inherit_fallback = str(value.value)
                elif isinstance(value, ast.List | ast.Tuple) and value.elts:
                    first = value.elts[0]
                    if isinstance(first, ast.Constant):
                        inherit_fallback = str(first.value)
                continue
            # <field> = fields.<Type>(...)
            if (
                isinstance(value, ast.Call)
                and isinstance(value.func, ast.Attribute)
                and isinstance(value.func.value, ast.Name)
                and value.func.value.id == "fields"
            ):
                fields_map[target.id] = value.func.attr
        model_name = name_explicit or inherit_fallback or node.name
        if fields_map:
            models[model_name] = fields_map
    return models


def _diff_path(base_ref: str, head_ref: str, path: str) -> list[str]:
    """Return markdown rows for one changed model file. Empty list when
    no field-level additions/removals are detected (rename-only edits,
    metadata-only changes, etc.)."""
    before = _git_show(base_ref, path) or ""
    after = _git_show(head_ref, path)
    if after is None:
        return []  # path deleted at head — the file-removal already shows in the diff
    old_models = _extract_models(before)
    new_models = _extract_models(after)
    rows: list[str] = []
    for model in sorted(set(old_models) | set(new_models)):
        old_fields = old_models.get(model, {})
        new_fields = new_models.get(model, {})
        for fname in sorted(set(new_fields) - set(old_fields)):
            rows.append(f"| + | `{model}` | `{fname}` | `{new_fields[fname]}` |")
        for fname in sorted(set(old_fields) - set(new_fields)):
            rows.append(f"| − | `{model}` | `{fname}` | `{old_fields[fname]}` |")
    return rows


def main() -> int:
    base = os.environ.get("BASE_SHA")
    head = os.environ.get("HEAD_SHA")
    if not (base and head):
        print("BASE_SHA and HEAD_SHA env vars required", file=sys.stderr)
        return 1

    # Find changed model files. `--diff-filter=ACMR` = added / copied /
    # modified / renamed. Deleted files (`D`) skip themselves earlier.
    proc = subprocess.run(
        [
            "git", "diff", "--name-only", "--diff-filter=ACMR",
            f"{base}..{head}", "--", "custom-addons/*/models/**.py",
        ],
        capture_output=True, text=True, check=True,
    )
    paths = [p.strip() for p in proc.stdout.splitlines() if p.strip()]
    if not paths:
        # Nothing changed under models/ — exit silently. The CI step
        # checks the script's stdout: empty → no comment posted.
        return 0

    sections: list[str] = []
    for path in paths:
        rows = _diff_path(base, head, path)
        if rows:
            sections.append(
                f"#### `{path}`\n\n"
                "| Action | Model | Field | Type |\n"
                "|---|---|---|---|\n" + "\n".join(rows)
            )

    if not sections:
        return 0  # no field-level changes — quiet exit

    print("## Schema diff (informational)\n")
    print(
        "Field additions / removals on changed "
        "`custom-addons/*/models/**.py` files. Type changes (e.g. "
        "`Char` → `Text`) and metadata edits are surfaced by the "
        "standard diff viewer — only the field-presence delta lives "
        "here.\n"
    )
    print("\n\n".join(sections))
    print(
        "\n<sub>Posted by `infra/scripts/schema_diff.py` "
        "(`.github/workflows/ci.yml::schema-diff`). Informational only — "
        "does not block merge.</sub>\n"
        "<!-- schema-diff -->"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
