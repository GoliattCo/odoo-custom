import type { Handler } from 'hono';

export const healthHandler: Handler = (c) => {
  return c.json({ ok: true, service: 'backup-runner' });
};
