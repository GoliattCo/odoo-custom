# 0004. Phase 1 retrospective — spec workflow enforcement bootstrap

**Date:** 2026-05-19
**Status:** Accepted

## Context

Phase 1 of the [spec-driven dev plan](../2026-05-15-spec-driven-dev-plan.md)
shipped the foundation layer: spec/plan/fix-brief templates, ADR scaffolding,
CODEOWNERS, the PR template, and six GHA enforcement workflows
(`spec-required`, `agent-guardrails`, `spec-quality`, `promote-to-prod`,
`rollback-prod`, `preview-cleanup`). Per §11 of the master plan, every phase
must close with a retrospective ADR capturing what was actually learned.

## Decision

Record the following as the Phase 1 outcome and let it inform Phase 2 onward.

### What landed

- **Templates:** `_TEMPLATE-design.md`, `_TEMPLATE-fix.md`, plans `_TEMPLATE.md`.
- **ADRs:** 0001 trunk-based-with-waves, 0002 cross-platform parity, 0003
  Better Stack log drain — all in `Accepted` state.
- **CODEOWNERS:** team-based layout under `@GoliattCo/*` slugs after the
  2026-05-19 org migration. Eight teams created
  (`maintainers`, `security-leads`, `prod-deployers`, `agent-team`,
  `senior-engineers`, `club-addon-owners`, `accounting-addon-owners`,
  `colombia-localization`); each has `@remcaro-rgb` as maintainer and push
  access to the repo (`prod-deployers`: maintain). Validated via
  `gh api repos/GoliattCo/odoo-custom/codeowners/errors` → `{"errors":[]}`.
- **Org migration:** `remcaro-rgb/odoo-custom` transferred to
  `GoliattCo/odoo-custom`. Operational references in `.github/SECRETS.md`,
  `infra/runbooks/move-tier.md`, and recent session docs updated to the new
  path. March-dated specs/plans intentionally left referencing the old
  owner as point-in-time records.
- **PR template:** `.github/PULL_REQUEST_TEMPLATE.md` with the v6 5-item
  CODEOWNERS checklist including the v5 reporter-ping clause (item 4).
- **CI gates (all parse-clean under strict pyyaml):**
  - `spec-required.yml` — blocks PRs that touch `custom-addons/`, `infra/`,
    workflows, or `Dockerfile` without a `Spec:` line, modulo
    `spec-exempt` label.
  - `agent-guardrails.yml` — enforces 12 hard rules on `agent/spec-*`
    branches (≤ 400 LOC, no infra edits, signed commits, test count must
    not shrink, spec-correction prefix audit, kill switch via
    `AGENTS_ENABLED`).
  - `spec-quality.yml` — template completeness, tenancy impact, open
    questions, regression-test sketches.
  - `promote-to-prod.yml`, `rollback-prod.yml`, `preview-cleanup.yml`
    — operational workflows referenced by later phases.
- **Kill switch:** repo variable `AGENTS_ENABLED=true` set; flipping to
  `false` halts all agent CI immediately.
- **CONTRIBUTING.md:** new file pointing developers at the templates and
  explaining the `spec-required` and `agent-guardrails` gates.

### What did not land, and why

- **Branch protection rules** (required status checks on `main` and
  `agent/spec-*`, linear history, signed commits, ≥ 1 CODEOWNERS approval,
  restricted pushes, refuse force-push on `agent/spec-*`). These are
  GitHub UI / repo-settings operations and require repo admin in a
  browser session; tracked as a separate operator follow-up. Without them
  the CI gates are advisory, not enforcing. **High-priority gap** —
  especially now that team-based CODEOWNERS exists and can actually
  enforce path-scoped review requirements once branch protection is wired.
- **`N=2` enforcement for security-sensitive paths.** Teams exist with the
  right structure, but `@remcaro-rgb` is currently the only member of
  every team. Enabling "Required approving reviews: 2" in branch
  protection (or a path-scoped Ruleset over `saas_tenant_gate/security/`
  and `agents/charters/`) would permanently block all PRs until the
  second human joins. Defer activation to first team hire; teams already
  carry the right shape.

### What we learned

- **YAML strictness bites quietly.** Two of the six workflows
  (`spec-required.yml`, `preview-cleanup.yml`) parsed in GitHub Actions
  but failed strict pyyaml — an unquoted colon in a step `name:` and a
  shell-style `\` line continuation that dedented out of a YAML block
  scalar. Both fixed during this phase. Add a `yamllint`/`actionlint`
  pre-commit hook in Phase 2 so future drift is caught locally.
- **CODEOWNERS placeholders aren't the only thing to grep for.** The
  pre-migration scaffold used `@remcaro-rgb` directly with `@your-org/*`
  only as documentation comments — the Phase 1 plan's "replace `@your-org`"
  step was a no-op against that file. After the GoliattCo migration the
  comments were the only useful artifact: they encoded the intended team
  layout, which made the rewrite a mechanical replacement rather than a
  fresh design pass.
- **`gh repo transfer` does not exist.** The repo-transfer subcommand
  isn't in the gh CLI; transfer must go through
  `gh api repos/<old>/<repo>/transfer -X POST -f new_owner=<new>`. API
  returns `202 Accepted` with the body still showing the old owner —
  verify the move by polling `gh api repos/<new>/<repo>` rather than
  trusting the immediate response.
- **Phase 1 is mostly process, but the YAML still needs to compile.**
  Two-thirds of execution time went to verifying the artefacts, not
  creating new ones. Future phases should budget time for activation
  (variable creation, label seeding, branch-protection clicks) on top of
  artefact authoring.

## Consequences

**Positive.**
- All future PRs touching addons/infra/workflows are gated by CI on a
  spec link.
- The kill switch is live: `gh variable set AGENTS_ENABLED --body false`
  stops all agent activity in one command.
- Subsequent phases can rely on the templates, ADR folder, and CODEOWNERS
  surface being present and well-formed.

**Negative.**
- Until branch protection is applied in repo settings, the
  `spec-required` and `agent-guardrails` checks are **non-blocking** —
  any maintainer can merge through a failed check. This is the most
  important Phase-1 follow-up.
- Team-based ownership is structurally present but functionally
  single-member. Security-sensitive paths route to `@GoliattCo/security-leads`,
  which has only `@remcaro-rgb` until the first hire — so the intended
  N=2 approval rule must remain disabled in branch protection or every
  PR blocks.

## Follow-ups (tracked separately)

1. Configure branch protection on `main` and on the `agent/spec-*`
   pattern per Phase 1 plan Tasks 7 & 8. Now unblocked: team slugs in
   CODEOWNERS resolve to real teams, so "Require review from Code Owners"
   becomes meaningful.
2. Add `yamllint` / `actionlint` as a pre-commit hook and CI step.
3. Re-run the Phase 1 verification checklist after branch protection is
   live (open a malformed PR; confirm CI blocks the merge button, not
   just shows a red check).
4. Re-point any external systems still trusting the old GitHub repo
   path: GHA OIDC subject claims in Vercel/Fly/Railway (sub:
   `repo:GoliattCo/odoo-custom:*`), Vercel project Git connection,
   webhooks. Audit during Phase 2 setup.
5. When first hire lands, flip "Required approving reviews" to 2 (or
   add a path-scoped Ruleset over the security paths).
