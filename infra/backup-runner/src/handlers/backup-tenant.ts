import { randomBytes } from 'node:crypto';
import { unlink } from 'node:fs/promises';
import * as os from 'node:os';
import * as path from 'node:path';

import type { Handler } from 'hono';
import { z } from 'zod';

import { pgCurrentWalLsn, pgDump } from '../pipeline/pg-dump.js';
import { filestoreTar } from '../pipeline/filestore-tar.js';
import { encryptArtifacts } from '../pipeline/encrypt.js';
import { uploadToS3 } from '../pipeline/upload.js';

const requestSchema = z.object({
  tenantId: z.string().uuid(),
  dbName: z.string().min(1).max(63),
  slug: z.string().regex(/^[a-z0-9][a-z0-9-]{1,38}[a-z0-9]$/),
  dekHex: z.string().regex(/^[0-9a-f]{64}$/),
  s3Bucket: z.string().min(1),
  s3Key: z.string().min(1),
  /** Phase 3: per-tenant cluster target. Shared tier omits this and the
   *  runner falls back to its default PG* env (shared pool). Exclusive
   *  tier sends the per-tenant Postgres internal hostname. */
  cluster: z
    .object({
      host: z.string().min(1),
      port: z.number().int().min(1).max(65535).default(5432),
      user: z.string().min(1).optional(),
      password: z.string().min(1).optional(),
    })
    .optional(),
});

export const backupTenantHandler: Handler = async (c) => {
  const raw = await c.req.json();
  const parsed = requestSchema.safeParse(raw);
  if (!parsed.success) {
    return c.json({ error: 'invalid-request', detail: parsed.error.flatten() }, 400);
  }
  const input = parsed.data;

  // Tempfiles for each artifact. We clean them up in `finally` even on error
  // so the runner volume doesn't fill up over time.
  const tmp = os.tmpdir();
  const runId = randomBytes(6).toString('hex');
  const dumpPath = path.join(tmp, `dump-${runId}.pgc`);
  const filestorePath = path.join(tmp, `filestore-${runId}.tar`);
  const encryptedPath = path.join(tmp, `enc-${runId}.bin`);

  try {
    // Phase 3 cluster routing: when input.cluster is present, override the
    // PG* env vars the pg_dump + psql child processes inherit. Each
    // override is scoped to this request — we do NOT mutate process.env
    // because other concurrent requests may target the default cluster.
    const pgEnv: Record<string, string> = input.cluster
      ? {
          PGHOST: input.cluster.host,
          PGPORT: String(input.cluster.port),
          ...(input.cluster.user ? { PGUSER: input.cluster.user } : {}),
          ...(input.cluster.password ? { PGPASSWORD: input.cluster.password } : {}),
        }
      : {};

    // Capture LSN before pg_dump so the catalog row has a recovery point that
    // bracket the dump from BEFORE its first read. Best-effort; pg_dump
    // itself takes a transactional snapshot, so this LSN is approximate.
    // Real LSN-precise atomicity needs pgBackRest's start_backup protocol,
    // tracked as Phase 2 work.
    const lsn = await pgCurrentWalLsn(pgEnv);

    const dump = await pgDump({ dbName: input.dbName, outputPath: dumpPath, env: pgEnv });

    const filestoreBase = process.env.FILESTORE_BASE ?? '/var/lib/odoo/filestore';
    const filestore = await filestoreTar({
      slug: input.slug,
      baseDir: filestoreBase,
      outputPath: filestorePath,
    });

    const dek = Buffer.from(input.dekHex, 'hex');
    const enc = await encryptArtifacts({
      dek,
      dump,
      filestore,
      outputPath: encryptedPath,
    });

    const upload = await uploadToS3({
      bucket: input.s3Bucket,
      key: input.s3Key,
      filePath: encryptedPath,
      sizeBytes: enc.sizeBytes,
      sha256Hex: enc.sha256Hex,
    });

    return c.json({
      storageUrl: upload.storageUrl,
      sizeBytes: enc.sizeBytes,
      sha256Hex: enc.sha256Hex,
      nonceHex: enc.nonceHex,
      tagHex: enc.tagHex,
      lsn,
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    console.error(`backup-tenant ${input.tenantId} failed: ${message}`);
    return c.json({ error: 'pipeline-failed', detail: message }, 500);
  } finally {
    // Best-effort cleanup. Ignore ENOENT — files may not exist if we failed
    // before producing them.
    await Promise.allSettled([unlink(dumpPath), unlink(filestorePath), unlink(encryptedPath)]);
  }
};
