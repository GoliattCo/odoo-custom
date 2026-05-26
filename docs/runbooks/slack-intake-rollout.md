# Slack Intake Bot — rollout runbook (Phases B → D)

**Owner:** DevOps + whoever's on this week's rotation.
**Parent plan:** [/Users/manuelcaro/.claude/plans/mutable-dancing-moon.md](../../../../Users/manuelcaro/.claude/plans/mutable-dancing-moon.md)
**Parent strategy doc:** [docs/2026-05-15-spec-driven-dev-plan.md §Q7](../2026-05-15-spec-driven-dev-plan.md)

Phase A landed the agent code, adapters, and tests in `agents/`. This runbook walks through bringing the bot up live on Fly (Phase B) and the two soak-gated rollout flips (C, D).

The kill switch through the whole rollout is the existing `AGENTS_ENABLED` repo variable. Flip it to `false` to refuse new deploys; set the Fly secret of the same name to `false` to make the running service return 503 to every webhook.

---

## Phase B — Stand up the bot in shadow mode

**Goal:** bot creates GitHub issues from Slack `/intake` but does NOT relay GH comments back. One-week soak window for the team to validate issue-body sanity.

### One-time bootstrap

```bash
# 1. Create the Fly app (org-owned, region iad).
flyctl apps create odoo-saas-slack-intake --org <your-org>

# 2. Create the SQLite volume.
./infra/fly/slack-intake/volume.sh

# 3. Configure the Slack app (https://api.slack.com/apps -> create).
#    Required:
#      Bot User OAuth Scopes:
#        commands, chat:write, chat:write.public,
#        channels:history, groups:history, im:history,
#        users:read, users:read.email, reactions:write
#      Slash Commands:  /intake  ->  https://odoo-saas-slack-intake.fly.dev/slack/commands
#      Event Subscriptions:
#        Request URL: https://odoo-saas-slack-intake.fly.dev/slack/events
#        Subscribe to: message.channels, message.groups, message.im
#      Interactivity:
#        Request URL: https://odoo-saas-slack-intake.fly.dev/slack/interactivity
#    Install the app to your workspace; copy the Bot User OAuth Token + Signing Secret.

# 4. Configure the GitHub org webhook
#    https://github.com/organizations/<your-org>/settings/hooks/new
#    Payload URL: https://odoo-saas-slack-intake.fly.dev/github/webhook
#    Content type: application/json
#    Secret: <generate one and store it>
#    Events: just "Issue comments"

# 5. Set the four Fly secrets.
flyctl secrets set --app odoo-saas-slack-intake \
  SLACK_BOT_TOKEN=xoxb-... \
  SLACK_SIGNING_SECRET=... \
  GITHUB_TOKEN=ghp_... \
  GITHUB_WEBHOOK_SECRET=...
# (See infra/fly/slack-intake/secrets.sample.env for the canonical list.)

# 6. First deploy. The Fly app config already has shadow_mode = true via
#    AGENTS_AGENTS_SLACK_INTAKE_SHADOW_MODE=true in fly.toml [env].
./infra/fly/slack-intake/deploy.sh
```

### Verification checklist (run once per environment)

1. `curl -fSs https://odoo-saas-slack-intake.fly.dev/healthz` returns `{"status":"ok"}`.
2. In Slack: `/intake` opens the modal in a channel listed in `slack_intake.allowed_channels` (config defaults to `[]` — start with one test channel ID).
3. Submit the modal. A new GitHub issue appears with labels `[bug|feature-request, severity:<x>, source:slack]`.
4. A confirmation message appears in the originating channel as a top-level reply.
5. `spec-generator-bot` (or whoever the configured author is) comments on the issue. Check the bot logs (`flyctl logs --app odoo-saas-slack-intake`) — you should see `slack_intake.shadow_mode_skip_relay`. Nothing should appear in the Slack thread.
6. Reply in the Slack thread. Nothing should appear on GitHub (Path C is gated on a non-shadow run too).

### Soak window — one week

Watch:
- `flyctl logs --app odoo-saas-slack-intake` for `slack_intake.issue_created` events. Confirm titles + labels + Slack permalink in the issue body look correct.
- GitHub PRs filed from Spec Generator on these intake-sourced issues — does the spec capture what the reporter actually meant?
- Slack #intake-test channel — is the modal UX clear? Any friction the team flags?

If anything looks wrong: flip `AGENTS_ENABLED` repo variable to `false`, fix on a branch, re-deploy.

---

## Phase C — Enable bidirectional relay on a single channel

**Goal:** flip `shadow_mode` off, but restrict the bot to one test channel for one more week of soak. Reporter Q&A loop is now live in Slack.

### Steps

1. Pick the test channel and grab its ID. In Slack, click the channel name → "About" → copy the `Cxxxxxxxx` ID.
2. Update the runtime config. Either commit a change to `agents/config.yml` (preferred) or set the Fly secret(s):
   ```bash
   flyctl secrets set --app odoo-saas-slack-intake \
     AGENTS_AGENTS_SLACK_INTAKE_SHADOW_MODE=false
   # allowed_channels is a list, harder to express as a single env var —
   # commit it in agents/config.yml under agents.slack_intake.allowed_channels
   ```
3. Re-deploy: `./infra/fly/slack-intake/deploy.sh`
4. Re-run the verification checklist, plus:
   - Spec Generator's comment now appears as a threaded reply with a "Confirm intent ✓" button.
   - Slack thread reply syncs back to GitHub as an attributed comment.
   - Clicking the button posts `/confirm` to the GitHub issue and edits the relayed card to "✅ Intent confirmed at <ts>".

### Soak window — one week

Watch (in addition to Phase B's metrics):
- `slack_intake.relayed_to_slack` and `slack_intake.relayed_to_github` log volumes — sanity-check that the loop is converging (Spec Generator's questions get answered, not infinite-looped).
- Click-through rate on the "Confirm intent" button vs. 24h-silence auto-confirm.
- Any reporter complaints about PII leaking either direction (the cheap PII mask is in place; if there's a real leak, flip back to `shadow_mode=true` immediately).

---

## Phase D — Roll workspace-wide

**Goal:** open the bot to all channels the team agrees to enrol. Operationally identical to Phase C — config change only.

### Steps

1. Decide the channel list with the team. Add their IDs (or just `"*"` if you want all public + private channels the bot is in).
2. Update `agents/config.yml`:
   ```yaml
   agents:
     slack_intake:
       allowed_channels: ["*"]    # or ["C0123", "C0124", ...]
   ```
3. Re-deploy: `./infra/fly/slack-intake/deploy.sh`
4. Announce in `#announcements` (or equivalent) that `/intake` is live workspace-wide. Link to a short doc explaining what the bot does.
5. Watch the success-metric dashboard for a week (median time intake → issue, modal abandonment, sensitive-topic refusals, 24h intent-confirm rate). Targets are in the parent plan's "Success metrics" section.

---

## Rollback decision tree

| Symptom | Action |
|---|---|
| Bot creates bad/spammy issues | Flip `shadow_mode` back to true; investigate. The intake path still works for collecting feedback. |
| Relay loops or duplicates GH comments | Set `AGENTS_ENABLED=false` on Fly to 503 every webhook; investigate the dedupe table. |
| Slack signature verification rejecting valid requests | Re-check `SLACK_SIGNING_SECRET` value; rotate if the app credentials were leaked. |
| Bot misses messages | Confirm the bot is a member of the channel (Slack Connect / private channels need an `/invite @intake-bot`). |
| PII leak in either direction | Flip `shadow_mode` true, update `infra/agentlab/mask-allowlist.yml`, re-deploy. |
| Total kill | `gh variable set AGENTS_ENABLED -b false` — refuses new deploys. Then `flyctl secrets set --app odoo-saas-slack-intake AGENTS_ENABLED=false` — running instance returns 503. |

---

## Reference

- Agent code: `agents/agents/slack_intake/`
- Adapters: `agents/agents/adapters/{events_slack_webhook,events_github_webhook,issues_github,state_sqlite,notifier_slack}.py`
- HTTP service: `agents/agents/services/slack_intake_http.py`
- Fly app: `infra/fly/slack-intake/`
- CI deploy: `.github/workflows/deploy-slack-intake.yml`
- Tests: `agents/tests/contract/test_*.py` + `agents/tests/integration/test_slack_intake_flow.py`
- Success metrics + open questions: parent plan at `/Users/manuelcaro/.claude/plans/mutable-dancing-moon.md`
