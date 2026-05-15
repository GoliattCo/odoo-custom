import { createDecipheriv } from 'node:crypto';
import { createReadStream, createWriteStream, statSync } from 'node:fs';

interface DecryptArtifactsArgs {
  dek: Buffer;          // 32 bytes
  nonce: Buffer;        // 12 bytes
  tag: Buffer;          // 16 bytes
  /** Encrypted package file produced by the encrypt pipeline. Layout:
   *  [32B encrypted header] [enc dump] [enc filestore] [16B GCM tag] */
  encryptedPath: string;
  /** Where to write the decrypted pg_dump custom-format archive. */
  dumpOutPath: string;
  /** Where to write the decrypted filestore tar. */
  filestoreOutPath: string;
}

interface DecryptArtifactsResult {
  dumpSize: number;
  filestoreSize: number;
}

const HEADER_BYTES = 32;
const TAG_BYTES = 16;
const HEADER_MAGIC = 'ODOO-SAAS-PKG-V1';

/**
 * Inverse of encrypt.ts. Reads the on-disk encrypted package, peels
 * the 16-byte GCM tag off the end, decrypts the header to learn the
 * dump + filestore byte ranges, then streams the two sub-artifacts out
 * to separate files.
 *
 * The GCM auth tag covers the WHOLE stream (header + dump + filestore),
 * so we must read every encrypted byte through the decipher in order
 * BEFORE calling final(). If anything is tampered, final() throws and
 * both output files are deleted by the caller.
 */
export async function decryptArtifacts(
  args: DecryptArtifactsArgs,
): Promise<DecryptArtifactsResult> {
  if (args.dek.length !== 32) throw new Error(`expected 32-byte DEK, got ${args.dek.length}`);
  if (args.nonce.length !== 12) throw new Error(`expected 12-byte nonce, got ${args.nonce.length}`);
  if (args.tag.length !== TAG_BYTES) throw new Error(`expected 16-byte tag, got ${args.tag.length}`);

  const totalSize = statSync(args.encryptedPath).size;
  if (totalSize < HEADER_BYTES + TAG_BYTES) {
    throw new Error(`encrypted file too short: ${totalSize} bytes`);
  }
  // The encrypt pipeline wrote the GCM tag as the LAST 16 bytes of the
  // file. We need to read exactly bytes [0, totalSize - 16) through the
  // decipher and pass `tag` to setAuthTag before final().
  const payloadEnd = totalSize - TAG_BYTES;

  const decipher = createDecipheriv('aes-256-gcm', args.dek, args.nonce);
  decipher.setAuthTag(args.tag);

  // Read enough plaintext to consume the 32-byte header first so we
  // know the dump + filestore boundaries. We stream chunks and route
  // plaintext bytes to the appropriate output: header → in-memory,
  // dump → dumpOut, filestore → filestoreOut.
  const headerBuf = Buffer.alloc(HEADER_BYTES);
  let headerFilled = 0;
  let dumpSize: number | null = null;
  let filestoreSize: number | null = null;
  let bytesEmittedAfterHeader = 0;

  const dumpOut = createWriteStream(args.dumpOutPath, { mode: 0o600 });
  const filestoreOut = createWriteStream(args.filestoreOutPath, { mode: 0o600 });

  const src = createReadStream(args.encryptedPath, {
    start: 0,
    end: payloadEnd - 1,           // inclusive end-byte; excludes the tag
    highWaterMark: 1 << 20,
  });

  await new Promise<void>((resolve, reject) => {
    src.on('error', reject);
    dumpOut.on('error', reject);
    filestoreOut.on('error', reject);

    src.on('data', (encChunk: Buffer | string) => {
      const buf = typeof encChunk === 'string' ? Buffer.from(encChunk) : encChunk;
      const plain = decipher.update(buf);
      routePlaintext(plain);
    });

    src.on('end', () => {
      try {
        const final = decipher.final();
        routePlaintext(final);
      } catch (err) {
        reject(err);
        return;
      }
      // Both writes share lifecycle; close in order.
      let pending = 2;
      const done = (err?: Error | null): void => {
        if (err) {
          reject(err);
          return;
        }
        pending -= 1;
        if (pending === 0) resolve();
      };
      dumpOut.end(done);
      filestoreOut.end(done);
    });

    function routePlaintext(buf: Buffer): void {
      let offset = 0;

      // Phase 1: fill the header.
      if (headerFilled < HEADER_BYTES) {
        const need = HEADER_BYTES - headerFilled;
        const take = Math.min(need, buf.length);
        buf.copy(headerBuf, headerFilled, 0, take);
        headerFilled += take;
        offset += take;

        if (headerFilled === HEADER_BYTES) {
          const magic = headerBuf.subarray(0, 16).toString('ascii');
          if (magic !== HEADER_MAGIC) {
            reject(new Error(`bad header magic: got "${magic}"`));
            return;
          }
          dumpSize = Number(headerBuf.readBigUInt64LE(16));
          filestoreSize = Number(headerBuf.readBigUInt64LE(24));
          if (!Number.isFinite(dumpSize) || !Number.isFinite(filestoreSize)) {
            reject(new Error('header lengths overflow Number'));
            return;
          }
        }
        if (offset >= buf.length) return;
      }

      // Phase 2: route remaining plaintext between dumpOut and filestoreOut.
      const remaining = buf.subarray(offset);
      if (remaining.length === 0) return;

      const dumpRemaining = (dumpSize ?? 0) - bytesEmittedAfterHeader;
      if (dumpRemaining > 0) {
        const toDump = remaining.subarray(0, Math.min(dumpRemaining, remaining.length));
        if (toDump.length > 0) {
          dumpOut.write(toDump);
          bytesEmittedAfterHeader += toDump.length;
        }
        if (toDump.length === remaining.length) return;
        const overflow = remaining.subarray(toDump.length);
        if (overflow.length > 0) {
          filestoreOut.write(overflow);
          bytesEmittedAfterHeader += overflow.length;
        }
      } else {
        filestoreOut.write(remaining);
        bytesEmittedAfterHeader += remaining.length;
      }
    }
  });

  if (dumpSize === null || filestoreSize === null) {
    throw new Error('header parsing did not complete');
  }
  return { dumpSize, filestoreSize };
}
