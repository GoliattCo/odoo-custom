// POST /v1/count-rows — read-only row count helper, cluster-routed.
//
// Used by moveTier's dumpSource (to capture source baseline) and
// verifyTarget (to compare against the baseline). Keeping this in the
// runner avoids opening up direct Postgres reachability from the control
// plane to the platform-internal cluster networks.

import { spawn } from 'node:child_process';

import type { Handler } from 'hono';
import { z } from 'zod';

const requestSchema = z.object({
  dbName: z.string().min(1).max(63),
  /** Tables to count. Identifiers are quoted at the SQL layer; we still
   *  enforce a strict regex here as a belt-and-braces guard. */
  tables: z
    .array(z.string().regex(/^[a-z_][a-z0-9_]*$/i).max(63))
    .min(1)
    .max(40),
  cluster: z.object({
    host: z.string().min(1),
    port: z.number().int().min(1).max(65535).default(5432),
    user: z.string().min(1).optional(),
    password: z.string().min(1).optional(),
  }),
});

export const countRowsHandler: Handler = async (c) => {
  const raw = await c.req.json();
  const parsed = requestSchema.safeParse(raw);
  if (!parsed.success) {
    return c.json({ error: 'invalid-request', detail: parsed.error.flatten() }, 400);
  }
  const input = parsed.data;

  const pgEnv: Record<string, string> = {
    PGHOST: input.cluster.host,
    PGPORT: String(input.cluster.port),
    ...(input.cluster.user ? { PGUSER: input.cluster.user } : {}),
    ...(input.cluster.password ? { PGPASSWORD: input.cluster.password } : {}),
  };

  // Compose one SELECT with UNION ALL across tables; one round-trip,
  // one snapshot.  Identifiers are quoted ("table") — z.string regex
  // already restricts to [a-z0-9_], no quoting bypass possible.
  const unionSql = input.tables
    .map((t) => `SELECT '${t}' AS tbl, count(*)::bigint AS n FROM "${t}"`)
    .join(' UNION ALL ');

  const proc = spawn(
    'psql',
    [
      '-t',                            // tuples only
      '-A',                            // unaligned
      '-F', '|',                       // pipe-delimited
      '-v', 'ON_ERROR_STOP=1',
      '-d', input.dbName,
      '-c', unionSql,
    ],
    {
      stdio: ['ignore', 'pipe', 'pipe'],
      env: { ...process.env, ...pgEnv },
    },
  );

  const out: Buffer[] = [];
  const err: Buffer[] = [];
  proc.stdout.on('data', (b: Buffer) => out.push(b));
  proc.stderr.on('data', (b: Buffer) => err.push(b));

  try {
    await new Promise<void>((resolve, reject) => {
      proc.on('error', reject);
      proc.on('exit', (code) => {
        if (code === 0) resolve();
        else reject(new Error(`psql count exited ${code}: ${Buffer.concat(err).toString('utf8').slice(0, 1000)}`));
      });
    });
  } catch (e) {
    const message = e instanceof Error ? e.message : String(e);
    return c.json({ error: 'query-failed', detail: message }, 500);
  }

  const counts: Record<string, number> = {};
  for (const line of Buffer.concat(out).toString('utf8').split('\n')) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    const [tbl, n] = trimmed.split('|');
    if (tbl && n) counts[tbl] = Number(n);
  }
  return c.json({ ok: true, counts });
};
