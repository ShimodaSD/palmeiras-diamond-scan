"""Coordinates source collection and notification decisions."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from .models import BRAZIL_TZ, TicketSaleEvent
from .notifier import (
    TelegramNotifier,
    build_empty_feed_message,
    build_message,
    build_source_failure_message,
    build_unparsed_message,
)
from .sources.base import SaleSource
from .sources.parsing import build_event_from_post, contains_ingresso, post_plain_text
from .storage import Storage


class Collector:
    """Fetches sale events, applies dedupe state, and sends notifications."""

    def __init__(
        self,
        sources: list[SaleSource],
        storage: Storage,
        notifier: TelegramNotifier,
        logger: logging.Logger,
        dry_run: bool = False,
        timezone: ZoneInfo | None = None,
    ) -> None:
        self.sources = sources
        self.storage = storage
        self.notifier = notifier
        self.logger = logger
        self.dry_run = dry_run
        self.timezone = timezone or BRAZIL_TZ

    def run_once(self, checked_at: datetime | None = None) -> list[TicketSaleEvent]:
        """Run a single collection pass and alert on new events or unparsed posts."""
        now = checked_at or datetime.now(self.timezone)
        sent: list[TicketSaleEvent] = []
        # On the very first pass, record existing posts without sending fallback
        # alerts, so deploying this feature does not spam the whole history.
        bootstrap = self.storage.count_posts() == 0
        seen_this_pass: set[str] = set()

        for source in self.sources:
            try:
                posts = source.fetch_posts()
            except Exception as exc:
                self.logger.exception("Source %s failed", source.name)
                self._alert_once(
                    f"source_failure:{source.name}:{now.date().isoformat()}",
                    build_source_failure_message(source.name, self._reason(exc), now),
                    now,
                )
                continue

            if not posts:
                self.logger.warning("Source %s returned no posts", source.name)
                self._alert_once(
                    f"empty_feed:{source.name}:{now.date().isoformat()}",
                    build_empty_feed_message(source.name, now),
                    now,
                )
                continue

            for post in posts:
                key = self._post_key(post)
                if key in seen_this_pass:
                    continue
                seen_this_pass.add(key)
                self._process_post(post, key, source, now, sent, bootstrap)

        return sent

    def _process_post(
        self,
        post: dict[str, Any],
        key: str,
        source: SaleSource,
        now: datetime,
        sent: list[TicketSaleEvent],
        bootstrap: bool,
    ) -> None:
        """Parse one post, notify when relevant, and record it as seen."""
        title, _, _ = post_plain_text(post)
        is_new = not self.storage.post_seen(key)
        event = build_event_from_post(post, source.name, source.lookback_days, now=now)

        if event is not None:
            self._notify_event(event, now, sent)
        elif is_new and not bootstrap and contains_ingresso(post):
            if not self._notify_unparsed(post, title):
                return

        if is_new and not self.dry_run:
            self.storage.record_post(
                post_key=key,
                source=source.name,
                title=title,
                url=post.get("link") or "",
                published_at=post.get("date"),
                modified_at=post.get("modified"),
                parsed=event is not None,
                first_seen_at=now.strftime("%Y-%m-%d %H:%M:%S"),
            )

    def _notify_event(
        self,
        event: TicketSaleEvent,
        now: datetime,
        sent: list[TicketSaleEvent],
    ) -> None:
        """Send a parsed event alert, isolating failures per event."""
        if self.storage.is_notified(event.match, event.sale_phase):
            return
        message = build_message(event, now)
        if self.dry_run:
            self.logger.info("[DRY RUN] would send:\n%s", message)
            sent.append(event)
            return
        try:
            self.notifier.send(message)
        except Exception:
            self.logger.exception("Failed to notify event: %s", event.match)
            return
        if self.storage.record(event, now.strftime("%Y-%m-%d %H:%M:%S")):
            self.logger.info(
                "Notification sent: %s | %s | %s | %s",
                event.match,
                event.venue_label,
                event.sale_phase,
                event.sale_start_at,
            )
            sent.append(event)

    def _notify_unparsed(self, post: dict[str, Any], title: str) -> bool:
        """Send the fallback alert for a new ticket post with no parsed schedule."""
        link = post.get("link") or ""
        published = (post.get("date") or "")[:10]
        message = build_unparsed_message(title, link, published)
        if self.dry_run:
            self.logger.info("[DRY RUN] would send fallback:\n%s", message)
            return True
        try:
            self.notifier.send(message)
        except Exception:
            self.logger.exception("Failed to send fallback alert: %s", link)
            return False
        self.logger.info("Fallback alert sent: %s | %s", title, link)
        return True

    def _alert_once(self, alert_key: str, message: str, now: datetime) -> None:
        """Send a health alert at most once per day for the same key."""
        if self.storage.alert_sent(alert_key):
            return
        if self.dry_run:
            self.logger.info("[DRY RUN] would send health alert:\n%s", message)
            return
        try:
            self.notifier.send(message)
        except Exception:
            self.logger.exception("Failed to send health alert: %s", alert_key)
            return
        self.storage.record_alert(alert_key, now.strftime("%Y-%m-%d %H:%M:%S"))
        self.logger.info("Health alert sent: %s", alert_key)

    @staticmethod
    def _reason(exc: Exception) -> str:
        """Short, log-safe reason for a source failure."""
        return f"{type(exc).__name__}: {exc}"[:200]

    @staticmethod
    def _post_key(post: dict[str, Any]) -> str:
        """Stable identity for a WordPress post."""
        return str(post.get("link") or post.get("id") or "")
