import { spawn } from 'node:child_process';
import { stat } from 'node:fs/promises';
import * as path from 'node:path';

interface FilestoreTarResult {
  path: string;
  size: number;
}

/**
 * tar the tenant's filestore directory. Odoo stores attachments under
 * <filestore_base>/<dbname>/.../<sha>; the tenant slug typically matches
 * the db name on the shared pool.
 *
 * Phase 1 limitation: not atomic with pg_dump. If Odoo writes attachments
 * while the tar runs, those new files MAY land in the tar but their
 * corresponding `ir.attachment` rows won't be in the dump (or vice versa).
 * Real atomicity needs pgBackRest's start/stop_backup protocol; this
 * helper documents the gap.
 */
export async function filestoreTar(args: {
  slug: string;
  baseDir: string;
  outputPath: string;
}): Promise<FilestoreTarResult> {
  const tenantDir = path.join(args.baseDir, args.slug);
  // -c  create
  // -f  output file
  // -C  change to base dir so paths inside the tar are relative
  // The slug is treated as a single arg; tar reads everything underneath.
  // (No compression here; encryption + S3 compress separately.)
  const proc = spawn(
    'tar',
    ['-cf', args.outputPath, '-C', args.baseDir, args.slug],
    { stdio: ['ignore', 'pipe', 'pipe'] },
  );

  const err: Buffer[] = [];
  proc.stderr.on('data', (c: Buffer) => err.push(c));

  await new Promise<void>((resolve, reject) => {
    proc.on('error', reject);
    proc.on('exit', (code) => {
      if (code === 0) {
        resolve();
      } else {
        reject(
          new Error(
            `tar exited ${code} (dir=${tenantDir}): ${Buffer.concat(err).toString('utf8').slice(0, 4000)}`,
          ),
        );
      }
    });
  });

  const stats = await stat(args.outputPath);
  return { path: args.outputPath, size: stats.size };
}
