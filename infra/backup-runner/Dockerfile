FROM node:22-alpine AS build

WORKDIR /app
COPY infra/backup-runner/package.json ./
RUN npm install --no-fund --no-audit

COPY infra/backup-runner/tsconfig.json ./
COPY infra/backup-runner/src ./src
RUN npx tsc

FROM node:22-alpine

LABEL org.opencontainers.image.title="odoo-saas-backup-runner"
LABEL org.opencontainers.image.description="HTTP service co-located with Postgres + the Odoo filestore; performs pg_dump + tar + encrypt + S3 upload for a single tenant on demand. Called by the WDK tenantBackupDaily workflow."

# postgresql16-client provides pg_dump + psql. tar is in busybox by default.
# ca-certificates needed for HTTPS to S3.
RUN apk add --no-cache postgresql16-client ca-certificates

WORKDIR /app
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/dist ./dist
COPY --from=build /app/package.json ./

# Non-root user. node:22-alpine ships with `node`/uid 1000 already; we
# delete that and create our own `odoo` user at the same uid so a shared
# filestore-volume permission set up for the Odoo image's user is readable
# here too. (Phase 1 doesn't actually mount the filestore on Fly because of
# the single-app-volume constraint, but keeping uid alignment costs nothing
# and makes the Railway / docker-compose paths work uniformly.)
RUN deluser --remove-home node 2>/dev/null || true \
    && addgroup -g 1000 odoo \
    && adduser -D -u 1000 -G odoo odoo

USER odoo

EXPOSE 8080

CMD ["node", "dist/server.js"]
