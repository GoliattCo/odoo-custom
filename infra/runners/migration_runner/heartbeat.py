"""Heartbeat thread for in-flight migrations.

While `runner.run_job()` blocks on the `odoo -u all` subprocess,
this thread:
1. Pings `heartbeat_at = now()` every HEARTBEAT_INTERVAL seconds so
   the Tier 3 sweeper doesn't reap us.
2. Reads the job's CURRENT status (RETURNING) — if Tier 1 cancelled
   the row, SIGTERMs the subprocess so the runner returns promptly.

Lifecycle:
    hb = HeartbeatThread(store, job_id, subprocess_pid)
    hb.start()
    ...subprocess runs...
    hb.stop()  # joins the thread
"""

from __future__ import annotations

import logging
import os
import signal
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL = 60.0  # seconds


class HeartbeatThread(threading.Thread):
    def __init__(
        self,
        store: object,
        job_id: str,
        subprocess_pid: Optional[int],
        *,
        interval: float = HEARTBEAT_INTERVAL,
        clock: Optional[object] = None,
    ) -> None:
        super().__init__(name=f'heartbeat-{job_id[:8]}', daemon=True)
        self._store = store
        self._job_id = job_id
        self._pid = subprocess_pid
        self._interval = interval
        self._stop_event = threading.Event()
        # Test seam: monkeypatchable clock + signal sender.
        self._clock = clock or time
        self._cancelled = False

    def stop(self) -> None:
        self._stop_event.set()
        self.join(timeout=self._interval * 2)

    @property
    def observed_cancel(self) -> bool:
        return self._cancelled

    def run(self) -> None:
        # First tick is immediate; subsequent waits are bounded by stop_event.
        while not self._stop_event.is_set():
            try:
                with self._store.cursor() as cur:  # type: ignore[attr-defined]
                    status = self._store.record_heartbeat(cur, self._job_id)  # type: ignore[attr-defined]
            except Exception:  # broad — heartbeat must NEVER kill the daemon
                logger.exception('heartbeat tick failed for job %s', self._job_id)
                status = None
            if status == 'cancelled':
                self._cancelled = True
                logger.warning(
                    'job %s flipped to cancelled — terminating subprocess pid=%s',
                    self._job_id,
                    self._pid,
                )
                if self._pid is not None:
                    try:
                        os.kill(self._pid, signal.SIGTERM)
                    except ProcessLookupError:
                        # Subprocess already exited — fine.
                        pass
                return
            # Sleep interval but wake up if stop() called early.
            self._stop_event.wait(self._interval)
