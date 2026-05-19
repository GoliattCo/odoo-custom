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
- **Branch protection on `main`** (classic protection): 6 required
  status checks (`Spec link present`, `Agent guardrails`, `Build Odoo
  image`, `Build Postgres image`, `Build Traefik image`,
  `saas_tenant_gate test suite`), `strict=true` (branch must be up to
  date), `enforce_admins=true` (no admin bypass), `required_linear_history`,
  `allow_force_pushes=false`, `allow_deletions=false`,
  `required_conversation_resolution=true`. Direct-push restriction
  scoped to the `prod-deployers` team. Spec-quality and the
  cross-platform deploy/parity jobs intentionally omitted from required
  checks — `spec-quality` is paths-filtered (would block any PR that
  doesn't touch specs), and `Deploy → Railway/Fly staging` +
  `Cross-platform parity gate` only run on push to main, not on PRs
  (would never report a status).
- **Ruleset for `agent/spec-*`** (id `16603187`, enforcement `active`):
  blocks deletion and non-fast-forward (no force-push, no history
  rewrite — satisfies §5.4.3.1 v5 invariant), requires signed commits
  (per §5.4.3.1), requires the 6 main checks plus `Spec quality
  checks`, and routes through PR review with conversation resolution.

### What did not land, and why

- **`N=2` enforcement deferred** — see next bullet for why this stays
  off until the first hire even though structurally it could be enabled
  today.
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
- Team-based ownership is structurally present but functionally
  single-member. Security-sensitive paths route to `@GoliattCo/security-leads`,
  which has only `@remcaro-rgb` until the first hire — so the intended
  N=2 approval rule must remain disabled in branch protection or every
  PR blocks.
- **Signed commits not required on `main`.** Local repo isn't set up
  for commit signing and every recent commit shows `%G? = N`. Enabling
  `required_signatures` on main right now would block the very PR that
  flips the switch. Tracked as a Phase 2 follow-up: set up
  SSH/GPG signing, backfill is unnecessary (signatures only verified
  going forward), then add the rule. Already required on
  `agent/spec-*` since no commits exist there yet and agents will be
  configured with signing keys when Phase 7 lands.
- **No automated audit yet** that the required check list stays in
  sync with the workflow job names. If a workflow renames a job, the
  required-check name silently drifts and PRs block forever.

## Follow-ups (tracked separately)

1. Add `yamllint` / `actionlint` as a pre-commit hook and CI step so the
   strict-YAML drift that bit `spec-required.yml` and `preview-cleanup.yml`
   never reaches a PR again.
2. Re-run the Phase 1 verification checklist (open a malformed PR;
   confirm the merge button is actually disabled, not just showing a
   red check).
3. Re-point external systems still trusting the old GitHub repo path:
   GHA OIDC subject claims in Vercel/Fly/Railway
   (sub: `repo:GoliattCo/odoo-custom:*`), Vercel project Git connection,
   webhooks. Audit during Phase 2 setup.
4. Set up commit signing locally (SSH or GPG via `gh ssh-key add` /
   `gpg --gen-key`), then add `required_signatures: true` to the `main`
   branch protection. No backfill needed — signatures are forward-only.
5. When first hire lands:
   - Flip `required_pull_request_reviews.required_approving_review_count`
     from 0 → 1 on `main`.
   - Flip `require_code_owner_reviews` to `true`.
   - For paths needing N=2 (`saas_tenant_gate/security/**`,
     `agents/charters/**`), add a path-scoped Ruleset with
     `required_approving_review_count: 2`.
6. Add a CI job that diffs the required-check list against the workflow
   job names — drift here silently blocks merges.
