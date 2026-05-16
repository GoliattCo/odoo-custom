// POST /v1/restore-tenant — inverse of /v1/backup-tenant.
//
// Called by the control plane's moveTier.restoreToTarget step (after
// dumpSource has produced an encrypted package on S3). The runner:
//   1. downloads the package from S3
//   2. decrypts it via AES-256-GCM with the supplied DEK + nonce + tag
//   3. routes the two embedded artifacts: pg_dump custom-format goes to
//      a tempfile, filestore tar goes to a sibling tempfile
//   4. pg_restore's the dump into the target cluster (clusterRef-routed)
//   5. discards the filestore tar — moveTier's separate `rsyncFilestore`
//      step handles filestore; this endpoint is DB-only
//
// The filestore tar in the encrypted package is the SOURCE-side filestore.
// We do NOT use it here because saas_filestore_backup's rsync handles
// the filestore copy independently. The decrypt step still has to walk
// past the filestore bytes (GCM auth covers the whole stream) but we
// throw the tar away after writing.

import { randomBytes } from 'node:crypto';
import { spawn } from 'node:child_process';
import { unlink } from 'node:fs/promises';
import * as os from 'node:os';
import * as path from 'node:path';

import type { Handler } from 'hono';
import { z } from 'zod';

import { downloadFromS3 } from '../pipeline/download.js';
import { decryptArtifacts } from '../pipeline/decrypt.js';
import { pgRestore } from '../pipeline/pg-restore.js';

const requestSchema = z.object({
  tenantId: z.string().uuid(),
  /** Target database name. Must already exist on the target cluster. */
  dbName: z.string().min(1).max(63),
  /** S3 location of the encrypted package produced by /v1/backup-tenant. */
  s3Bucket: z.string().min(1),
  s3Key: z.string().min(1),
  dekHex: z.string().regex(/^[0-9a-f]{64}$/),
  nonceHex: z.string().regex(/^[0-9a-f]{24}$/),
  tagHex: z.string().regex(/^[0-9a-f]{32}$/),
  /** Phase 3 cluster routing (REQUIRED for restore — we're always
   *  targeting a per-tenant cluster, not the shared pool). */
  cluster: z.object({
    host: z.string().min(1),
    port: z.number().int().min(1).max(65535).default(5432),
    user: z.string().min(1).optional(),
    password: z.string().min(1).optional(),
  }),
  /** Phase 3.0 v0.3: when true, runs `CREATE DATABASE <dbName>` against
   *  the cluster's `postgres` maintenance DB before pg_restore. Required
   *  for moveTier — per-tenant clusters boot with only the default db. */
  createDatabase: z.boolean().default(false),
});

export const restoreTenantHandler: Handler = async (c) => {
  const raw = await c.req.json();
  const parsed = requestSchema.safeParse(raw);
  if (!parsed.success) {
    return c.json({ error: 'invalid-request', detail: parsed.error.flatten() }, 400);
  }
  const input = parsed.data;

  const tmp = os.tmpdir();
  const runId = randomBytes(6).toString('hex');
  const encPath = path.join(tmp, `enc-${runId}.bin`);
  const dumpPath = path.join(tmp, `dump-${runId}.pgc`);
  const filestorePath = path.join(tmp, `filestore-${runId}.tar`);

  try {
    await downloadFromS3({
      bucket: input.s3Bucket,
      key: input.s3Key,
      destPath: encPath,
    });

    const dek = Buffer.from(input.dekHex, 'hex');
    const nonce = Buffer.from(input.nonceHex, 'hex');
    const tag = Buffer.from(input.tagHex, 'hex');
    const sizes = await decryptArtifacts({
      dek,
      nonce,
      tag,
      encryptedPath: encPath,
      dumpOutPath: dumpPath,
      filestoreOutPath: filestorePath,
    });

    const pgEnv: Record<string, string> = {
      PGHOST: input.cluster.host,
      PGPORT: String(input.cluster.port),
      ...(input.cluster.user ? { PGUSER: input.cluster.user } : {}),
      ...(input.cluster.password ? { PGPASSWORD: input.cluster.password } : {}),
    };

    // Phase 3.0 v0.3: create the target DB before pg_restore. Connects
    // to the `postgres` maintenance DB on the SAME cluster using the
    // same credentials. Idempotent — IF NOT EXISTS would be nicer but
    // PG doesn't support it for CREATE DATABASE; we catch the
    // duplicate_database SQLSTATE explicitly.
    if (input.createDatabase) {
      await createDbIfMissing({ dbName: input.dbName, env: pgEnv });
    }

    await pgRestore({
      dumpPath,
      dbName: input.dbName,
      env: pgEnv,
    });

    return c.json({
      ok: true,
      dumpSize: sizes.dumpSize,
      filestoreSize: sizes.filestoreSize,
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    console.error(`restore-tenant ${input.tenantId} failed: ${message}`);
    return c.json({ error: 'restore-failed', detail: message }, 500);
  } finally {
    await Promise.allSettled([unlink(encPath), unlink(dumpPath), unlink(filestorePath)]);
  }
};

/** psql -d postgres -c "CREATE DATABASE <db>". On duplicate_database
 *  (42P04), succeed silently — supports re-runs of the restore step. */
async function createDbIfMissing(args: {
  dbName: string;
  env: Record<string, string>;
}): Promise<void> {
  // db name is locked to /^[a-z][a-z0-9_-]{1,62}$/ at the request boundary
  // (DB_NAME regex), so no escaping bypass risk in the inlined name.
  const proc = spawn(
    'psql',
    [
      '-d', 'postgres',
      '-v', 'ON_ERROR_STOP=1',
      '-c', `CREATE DATABASE "${args.dbName}"`,
    ],
    { stdio: ['ignore', 'pipe', 'pipe'], env: { ...process.env, ...args.env } },
  );
  const err: Buffer[] = [];
  proc.stderr.on('data', (b: Buffer) => err.push(b));
  await new Promise<void>((resolve, reject) => {
    proc.on('error', reject);
    proc.on('exit', (code) => {
      if (code === 0) {
        resolve();
        return;
      }
      const tail = Buffer.concat(err).toString('utf8');
      // duplicate_database — fine, already exists from a previous attempt
      if (/already exists|duplicate_database|42P04/i.test(tail)) {
        resolve();
        return;
      }
      reject(new Error(`createDatabase exited ${code}: ${tail.slice(0, 1000)}`));
    });
  });
}
