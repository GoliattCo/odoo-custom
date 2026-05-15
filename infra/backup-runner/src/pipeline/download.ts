import { createWriteStream } from 'node:fs';
import { pipeline } from 'node:stream/promises';

import { GetObjectCommand, S3Client } from '@aws-sdk/client-s3';

const s3 = new S3Client({ region: process.env.AWS_REGION });

interface DownloadFromS3Args {
  bucket: string;
  key: string;
  destPath: string;
}

interface DownloadFromS3Result {
  sizeBytes: number;
}

/**
 * Streams the S3 object to a local file. No checksum verification here —
 * the decrypt step's AES-GCM tag is the load-bearing integrity check;
 * sha256 cross-check is a control-plane concern that already happens via
 * the catalog row before /v1/restore-tenant is even called.
 */
export async function downloadFromS3(args: DownloadFromS3Args): Promise<DownloadFromS3Result> {
  const out = await s3.send(
    new GetObjectCommand({ Bucket: args.bucket, Key: args.key }),
  );
  if (!out.Body) {
    throw new Error(`S3 GetObject returned empty Body for s3://${args.bucket}/${args.key}`);
  }
  const dest = createWriteStream(args.destPath, { mode: 0o600 });
  await pipeline(out.Body as unknown as NodeJS.ReadableStream, dest);
  return { sizeBytes: out.ContentLength ?? 0 };
}
