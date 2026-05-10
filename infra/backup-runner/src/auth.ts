import type { MiddlewareHandler } from 'hono';

// Bearer-token gate. The token comes from BACKUP_RUNNER_TOKEN env var (set
// alongside the runner in the platform's secret store) and must match the
// token the control plane sends from its own env. Rotation procedure: pick
// a new token, set it on both ends within the same maintenance window.
export const bearerAuth: MiddlewareHandler = async (c, next) => {
  const expected = process.env.BACKUP_RUNNER_TOKEN;
  if (!expected) {
    return c.json({ error: 'runner-token-unset' }, 503);
  }
  const auth = c.req.header('authorization');
  if (auth !== `Bearer ${expected}`) {
    // Constant 401 — never disclose whether the token was present-but-wrong
    // vs missing entirely. Both look identical to the caller.
    return c.json({ error: 'unauthorized' }, 401);
  }
  await next();
};
