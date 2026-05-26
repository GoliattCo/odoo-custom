#!/usr/bin/env bash
# Idempotently provision the SQLite volume for odoo-saas-slack-intake.
#
# The Fly volume holds the slack_intake.db file. Re-running this script is
# safe: it lists existing volumes first and only creates one if absent.
#
# Usage:
#   ./infra/fly/slack-intake/volume.sh
#
# Requirements:
#   flyctl auth login   (with org access to the app)
#   The Fly app `odoo-saas-slack-intake` must already exist
#   (run `flyctl apps create odoo-saas-slack-intake --org <your-org>`).

set -euo pipefail

APP="odoo-saas-slack-intake"
VOLUME="slack_intake_data"
REGION="iad"
SIZE_GB=1

existing=$(flyctl volumes list --app "$APP" --json 2>/dev/null \
  | grep -c "\"name\":\"$VOLUME\"" || true)

if [ "$existing" -gt 0 ]; then
  echo "Volume $VOLUME already exists on $APP — nothing to do."
  exit 0
fi

echo "Creating volume $VOLUME ($SIZE_GB GB, region $REGION) on $APP …"
flyctl volumes create "$VOLUME" \
  --app "$APP" \
  --region "$REGION" \
  --size "$SIZE_GB" \
  --yes

echo "Done. Confirm with: flyctl volumes list --app $APP"
