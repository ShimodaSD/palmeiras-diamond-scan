"""Coordinates source collection and notification decisions."""

from __future__ import annotations

import logging
from datetime import datetime

from .models import BRAZIL_TZ, TicketSaleEvent
from .notifier import TelegramNotifier, build_message
from .storage import Storage
from .sources.base import SaleSource


class Collector:
    """Fetches sale events, applies dedupe state, and sends notifications."""

    def __init__(
        self,
        sources: list[SaleSource],
        storage: Storage,
        notifier: TelegramNotifier,
        logger: logging.Logger,
        dry_run: bool = False,
    ) -> None:
        self.sources = sources
        self.storage = storage
        self.notifier = notifier
        self.logger = logger
        self.dry_run = dry_run

    def run_once(self, checked_at: datetime | None = None) -> list[TicketSaleEvent]:
        """Run a single collection pass and send notifications for new events."""
        now = checked_at or datetime.now(BRAZIL_TZ)
        sent: list[TicketSaleEvent] = []
        seen: set[tuple[str, str]] = set()
        for source in self.sources:
            for event in source.fetch_sale_events():
                key = (event.match, event.sale_phase)
                if key in seen or self.storage.is_notified(event.match, event.sale_phase):
                    continue
                seen.add(key)
                message = build_message(event, now)
                if self.dry_run:
                    self.logger.info("[DRY RUN] would send:\n%s", message)
                    sent.append(event)
                    continue
                self.notifier.send(message)
                if self.storage.record(event, now.strftime("%Y-%m-%d %H:%M:%S")):
                    self.logger.info(
                        "Notification sent: %s | %s | %s",
                        event.match,
                        event.sale_phase,
                        event.sale_start_at,
                    )
                    sent.append(event)
        return sent
