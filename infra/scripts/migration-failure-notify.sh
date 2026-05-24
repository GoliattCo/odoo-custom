#!/bin/bash
# Phase 4 (Tier 6) — Slack notification on tenant_migration_job failure.
#
# Called by the runner daemon's finalize_failed path. Posts a single
# Slack message to #devops-implementations summarising the failure.
# The runner has already paged on-call via the page_oncall() stub
# (Tier 2); this script is the broader visibility layer.
#
# Usage:
#   infra/scripts/migration-failure-notify.sh \
#     --tenant-slug acme \
#     --target-sha deadbeef1234 \
#     --status timedout \
#     --job-id 99999999-9999-9999-9999-999999999999 \
#     --error "exit=124 timed out after 1800s"
#
# Required env:
#   DEVOPS_SLACK_WEBHOOK_URL   webhook for #devops-implementations
#
# Exits 0 silently when the webhook URL is unset — so a missing secret
# can't crash a successful finalize transaction.

set -euo pipefail

if [ -z "${DEVOPS_SLACK_WEBHOOK_URL:-}" ]; then
  echo "DEVOPS_SLACK_WEBHOOK_URL unset — skipping Slack notify" >&2
  exit 0
fi

TENANT_SLUG=""
TARGET_SHA=""
STATUS=""
JOB_ID=""
ERROR=""
OPERATOR_UI_BASE="${OPERATOR_UI_BASE:-https://odoo-saas-admin.vercel.app}"

while [ $# -gt 0 ]; do
  case "$1" in
    --tenant-slug)  TENANT_SLUG="$2"; shift 2 ;;
    --target-sha)   TARGET_SHA="$2";  shift 2 ;;
    --status)       STATUS="$2";      shift 2 ;;
    --job-id)       JOB_ID="$2";      shift 2 ;;
    --error)        ERROR="$2";       shift 2 ;;
    *) echo "unknown arg: $1" >&2; exit 1 ;;
  esac
done

# Truncate error excerpt to ~500 chars so Slack doesn't reject the
# payload. Slack's text limit is 40KB but readability beats fidelity.
ERROR_TRUNC="${ERROR:0:500}"
if [ ${#ERROR} -gt 500 ]; then
  ERROR_TRUNC="${ERROR_TRUNC}…(${#ERROR} chars total)"
fi

# Compose a Slack blocks payload — easier to skim than a wall of text.
PAYLOAD=$(cat <<EOF
{
  "text": "Migration job ${STATUS}: ${TENANT_SLUG} → ${TARGET_SHA}",
  "blocks": [
    {
      "type": "header",
      "text": { "type": "plain_text", "text": "Migration ${STATUS}: ${TENANT_SLUG}" }
    },
    {
      "type": "section",
      "fields": [
        { "type": "mrkdwn", "text": "*Tenant:*\n\`${TENANT_SLUG}\`" },
        { "type": "mrkdwn", "text": "*Target SHA:*\n\`${TARGET_SHA}\`" },
        { "type": "mrkdwn", "text": "*Status:*\n\`${STATUS}\`" },
        { "type": "mrkdwn", "text": "*Job ID:*\n\`${JOB_ID}\`" }
      ]
    },
    {
      "type": "section",
      "text": { "type": "mrkdwn", "text": "*Error:*\n\`\`\`${ERROR_TRUNC}\`\`\`" }
    },
    {
      "type": "actions",
      "elements": [
        {
          "type": "button",
          "text": { "type": "plain_text", "text": "Open in operator UI" },
          "url": "${OPERATOR_UI_BASE}/migrations?status=${STATUS}"
        }
      ]
    }
  ]
}
EOF
)

curl -sS -X POST -H "Content-Type: application/json" \
  --data "$PAYLOAD" \
  "$DEVOPS_SLACK_WEBHOOK_URL"
echo  # newline after the OK
