import { createReadStream } from 'node:fs';

import { S3Client } from '@aws-sdk/client-s3';
import { Upload } from '@aws-sdk/lib-storage';

const s3 = new S3Client({ region: process.env.AWS_REGION });

interface UploadToS3Args {
  bucket: string;
  key: string;
  filePath: string;
  sizeBytes: number;
  sha256Hex: string;
}

interface UploadToS3Result {
  storageUrl: string;
}

/**
 * Multipart-aware S3 upload. Files under 5 GB go single-part; larger files
 * automatically split via `@aws-sdk/lib-storage::Upload`.
 *
 * - `ChecksumAlgorithm: 'SHA256'` makes S3 compute its own per-part SHA-256.
 * - `Metadata.sha256` carries the runner's whole-file SHA-256 (matches the
 *   catalog row in Neon).
 */
export async function uploadToS3(args: UploadToS3Args): Promise<UploadToS3Result> {
  const upload = new Upload({
    client: s3,
    params: {
      Bucket: args.bucket,
      Key: args.key,
      Body: createReadStream(args.filePath),
      ContentLength: args.sizeBytes,
      ChecksumAlgorithm: 'SHA256',
      Metadata: { sha256: args.sha256Hex },
    },
  });
  await upload.done();
  return { storageUrl: `s3://${args.bucket}/${args.key}` };
}
