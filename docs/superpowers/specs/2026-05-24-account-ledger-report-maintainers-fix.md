# `account_ledger_report` — add `maintainers` + `author` fields to the manifest

**Date:** 2026-05-24
**Author:** Tier-7 post-merge live validation (commit hygiene fix)
**Status:** In Review
**Spec type:** fix-brief
**Linked issue:** N/A — validates the comment-after-push + dedup refactor (commit `66eb371`)
**Severity:** low

---

## 1. Symptom

`custom-addons/account_ledger_report/__manifest__.py` is missing both
the `author` and `maintainers` metadata fields. Both are project
conventions present on most addons.

## 2. Repro

1. `cat custom-addons/account_ledger_report/__manifest__.py`
2. Neither `'author'` nor `'maintainers'` keys are present.

**Reproduced on:** working tree at HEAD of main.

## 3. Affected tenants & severity

- **Tenants impacted:** none — manifest metadata only.
- **Severity:** low.
- **Workaround:** n/a — hygiene fix.

## 4. Root cause

Manifest hygiene. `account_ledger_report` predates the metadata
convention; adding `author` + `maintainers` brings it in line.

## 5. Proposed fix

Add the two keys to `custom-addons/account_ledger_report/__manifest__.py`,
placed near the other metadata:

```python
'author': 'Manuel Caro',
'maintainers': ['Manuel Caro'],
```

Place them between `summary` and `category` (or `category` and
`depends` — same effect). No other changes.

## 6. Regression test

```python
# custom-addons/account_ledger_report/tests/test_manifest.py
import ast
from odoo.tests import TransactionCase, tagged
from odoo.tools import file_open


@tagged('-at_install', 'post_install')
class TestManifest(TransactionCase):
    def test_author_and_maintainers_are_set(self):
        with file_open('account_ledger_report/__manifest__.py', 'r') as fh:
            manifest = ast.literal_eval(fh.read())
        assert manifest.get('author'), 'author must be set'
        maintainers = manifest.get('maintainers')
        self.assertIsInstance(maintainers, list)
        self.assertTrue(maintainers, 'maintainers list must not be empty')
```

## 7. Rollout

- Severity = low → ride the next normal wave.
- Expected outcomes (validation of Tier-7 commit `66eb371`):
  - Bot commit lands on the PR branch authored by
    `implementation-bot[bot]`.
  - **EXACTLY ONE** "I've implemented this spec and pushed the code"
    bot comment posts, with timestamp AFTER the bot's commit timestamp
    (the comment now follows the push instead of preceding it).
  - Re-toggling `intent-confirmed` does NOT post a second success
    comment — the dedup check (`Implemented \`<spec>\`.` marker) wins.
  - `outcome { status: implemented }` event in the run log.
  - No `needs-human` label.
