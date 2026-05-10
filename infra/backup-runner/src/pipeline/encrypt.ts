import { createCipheriv, createHash, randomBytes } from 'node:crypto';
import { createReadStream, createWriteStream } from 'node:fs';
import { stat } from 'node:fs/promises';

interface EncryptArtifactsArgs {
  dek: Buffer;        // 32 bytes
  dump: { path: string; size: number };
  filestore: { path: string; size: number };
  outputPath: string;
}

interface EncryptArtifactsResult {
  sizeBytes: number;
  sha256Hex: string;
  nonceHex: string;
  tagHex: string;
}

/**
 * Stream-encrypt the dump + filestore artifacts into a single output file
 * with AES-256-GCM. File layout:
 *
 *   [32B encrypted header: 16B ASCII magic "ODOO-SAAS-PKG-V1"
 *                          8B LE u64 dump.size
 *                          8B LE u64 filestore.size]
 *   [encrypted dump bytes (dump.size)]
 *   [encrypted filestore bytes (filestore.size)]
 *   [16B GCM auth tag]
 *
 * The format matches the one originally documented in the control plane's
 * runEncryptPackage step so existing restore tooling for the format keeps
 * working when the runner takes over.
 *
 * sha256 is computed over the FINAL on-disk file (including the appended
 * tag) so the catalog and S3 metadata agree on a single byte stream.
 */
export async function encryptArtifacts(
  args: EncryptArtifactsArgs,
): Promise<EncryptArtifactsResult> {
  if (args.dek.length !== 32) {
    throw new Error(`expected 32-byte DEK, got ${args.dek.length}`);
  }

  const nonce = randomBytes(12);
  const cipher = createCipheriv('aes-256-gcm', args.dek, nonce);
  const output = createWriteStream(args.outputPath);

  const header = Buffer.alloc(32);
  header.write('ODOO-SAAS-PKG-V1', 0, 16, 'ascii');
  header.writeBigUInt64LE(BigInt(args.dump.size), 16);
  header.writeBigUInt64LE(BigInt(args.filestore.size), 24);
  output.write(cipher.update(header));

  for await (const chunk of createReadStream(args.dump.path)) {
    output.write(cipher.update(chunk as Buffer));
  }
  for await (const chunk of createReadStream(args.filestore.path)) {
    output.write(cipher.update(chunk as Buffer));
  }
  output.write(cipher.final());
  const tag = cipher.getAuthTag();
  output.write(tag);

  await new Promise<void>((resolve, reject) => {
    output.end((err?: Error | null) => (err ? reject(err) : resolve()));
  });

  // Stream a hash over the final file for the catalog row. Done after the
  // write so we capture the appended tag too.
  const hash = createHash('sha256');
  for await (const chunk of createReadStream(args.outputPath)) {
    hash.update(chunk as Buffer);
  }
  const stats = await stat(args.outputPath);

  return {
    sizeBytes: stats.size,
    sha256Hex: hash.digest('hex'),
    nonceHex: nonce.toString('hex'),
    tagHex: tag.toString('hex'),
  };
}
