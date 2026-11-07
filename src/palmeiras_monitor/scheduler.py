"""Simple polling scheduler for the ticket monitor."""

from __future__ import annotations

import logging
import threading
import time

logger = logging.getLogger("palmeiras_monitor")


class TicketMonitorScheduler:
    """Runs the collector on a fixed interval until stopped."""

    def __init__(self, interval_seconds: int, handler) -> None:
        self.interval_seconds = interval_seconds
        self.handler = handler
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the scheduler loop in a background thread."""
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="palmeiras-monitor", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.handler()
            except Exception:
                logger.exception("Scheduled collection pass failed")
            self._stop_event.wait(self.interval_seconds)

    def stop(self) -> None:
        """Signal the scheduler loop to stop and wait briefly."""
        self._stop_event.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=10)

    def is_running(self) -> bool:
        """Return True while the scheduler thread is alive."""
        return self._thread is not None and self._thread.is_alive()
