#!/usr/bin/env python3
"""Rewrite the host:port of a Postgres connection URI, keeping everything else.

Used by .github/workflows/agentlab-daily-restore.yml: the agentlab (and
optionally the staging) Postgres live on Fly's private 6PN network, so the
workflow opens a `flyctl proxy` tunnel to 127.0.0.1:<port> and then needs
the committed DSN secret repointed at that local address — user, password,
database name, and query string all preserved.

Usage:
    dsn_rewrite_host.py <dsn> <new-host:port>

Prints the rewritten DSN to stdout.
"""

import sys
from urllib.parse import urlparse, urlunparse


def rewrite_host(dsn: str, hostport: str) -> str:
    """Return `dsn` with its netloc host:port replaced by `hostport`.

    The userinfo (user:password) segment and everything after the
    authority — path (database), query, fragment — are left untouched.
    """
    parsed = urlparse(dsn)
    userinfo = ""
    if "@" in parsed.netloc:
        userinfo = parsed.netloc.rsplit("@", 1)[0] + "@"
    return urlunparse(parsed._replace(netloc=userinfo + hostport))


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        sys.exit(2)
    print(rewrite_host(sys.argv[1], sys.argv[2]))
