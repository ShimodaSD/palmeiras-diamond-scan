"""Coordinates source collection and notification decisions."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from .models import BRAZIL_TZ, TicketSaleEvent, post_identity
from .notifier import (
    TelegramNotifier,
    build_empty_feed_message,
    build_message,
    build_sale_change_message,
    build_sale_change_message,
    build_source_failure_message,
    build_store_open_message,
    build_unparsed_message,
    build_updated_message,
)
from .sources.base import SaleSource
from .sources.parsing import (
    build_event_from_post,
    contains_ingresso,
    extract_teams,
    post_plain_text,
)
from .sources.store import TicketStoreSource
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
        store_source: TicketStoreSource | None = None,
    ) -> None:
        self.sources = sources
        self.storage = storage
        self.notifier = notifier
        self.logger = logger
        self.dry_run = dry_run
        self.timezone = timezone or BRAZIL_TZ
        self.store_source = store_source

    def run_once(self, checked_at: datetime | None = None) -> list[TicketSaleEvent]:
        """Run a single collection pass and alert on new events or unparsed posts."""
        now = checked_at or datetime.now(self.timezone)
        if not self.storage.acquire_run_lock():
            self.logger.warning("Collection pass skipped: another monitor instance is active")
            return []
        try:
            return self._run_once(now)
        finally:
            self.storage.release_run_lock()

    def _run_once(self, now: datetime) -> list[TicketSaleEvent]:
        sent: list[TicketSaleEvent] = []
        # On the very first pass, record existing posts without sending fallback
        # alerts, so deploying this feature does not spam the whole history.
        bootstrap = self.storage.count_posts() == 0
        seen_this_pass: set[str] = set()
        store_status = None
        self._retry_pending_alerts(now)

        try:
            store_status = self.store_source.check() if self.store_source else None
        except Exception as exc:
            self.logger.exception("Ticket store probe failed")
            self._alert_once(
                f"source_failure:{self.store_source.name if self.store_source else 'ticket_store'}:{now.date().isoformat()}",
                build_source_failure_message(
                    self.store_source.name if self.store_source else "ticket_store",
                    self._reason(exc),
                    now,
                ),
                now,
            )
        store_announcement_url = None
        store_match = None
        store_announcement_date = ""
        matched_store_event = False

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
                event = self._process_post(post, key, source, now, sent, bootstrap)
                if (
                    store_status
                    and store_status.active
                    and post.get("link")
                    and contains_ingresso(post)
                ):
                    published = post.get("date") or ""
                    title, _, text = post_plain_text(post)
                    matching_event = (
                        event
                        and store_status.sale_start_at
                        and event.sale_start_at
                        == store_status.sale_start_at.isoformat(timespec="minutes")
                    )
                    if matching_event:
                        store_announcement_url = event.announcement_url
                        store_match = event.match
                        matched_store_event = True
                    elif not matched_store_event and published > store_announcement_date:
                        store_announcement_url = post["link"]
                        store_match = extract_teams(f"{title}\n{text}")
                        store_announcement_date = published

        if store_status and store_status.active:
            event_key = store_status.event_key or "queue"
            alert_key = f"store_open:{event_key}"
            if not store_announcement_url:
                self.logger.warning("Queue detected but no official ticket announcement link was found")
            elif not self.storage.store_event_seen(alert_key):
                message = build_store_open_message(
                    store_status.sale_start_at,
                    store_status.target_url,
                    store_announcement_url,
                    store_match,
                    now,
                )
                if self._send_alert(message, alert_key, now):
                    self.storage.record_store_event(
                        alert_key, now.strftime("%Y-%m-%d %H:%M:%S")
                    )

        return sent

    def _process_post(
        self,
        post: dict[str, Any],
        key: str,
        source: SaleSource,
        now: datetime,
        sent: list[TicketSaleEvent],
        bootstrap: bool,
    ) -> TicketSaleEvent | None:
        """Parse one post, notify when relevant, and record it as seen."""
        title, _, _ = post_plain_text(post)
        previous = self.storage.get_post(key)
        is_new = previous is None
        modified = post.get("modified")
        edited = previous is not None and modified and modified != previous["modified_at"]
        event = build_event_from_post(post, source.name, source.lookback_days, now=now)

        if edited and contains_ingresso(post):
            if event is not None:
                if not self._notify_update(event, now):
                    return
            elif not self._notify_unparsed(post, title):
                return
        elif event is not None:
            self._notify_event(event, now, sent)
        elif is_new and not bootstrap and contains_ingresso(post):
            if not self._notify_unparsed(post, title):
                return None

        if (is_new or edited) and not self.dry_run:
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
        return event

    def _notify_update(self, event: TicketSaleEvent, now: datetime) -> bool:
        """Send an update for a changed ticket post, retrying until delivered."""
        previous = self.storage.get_notification(event.dedupe_key)
        if previous and previous["sale_start_at"] != event.sale_start_at:
            message = build_sale_change_message(event, previous["sale_start_at"], now)
        elif previous:
            message = build_updated_message(event, now)
        else:
            message = build_message(event, now)
        if self.dry_run:
            self.logger.info("[DRY RUN] would send update:\n%s", message)
            return True
        try:
            self.notifier.send(message)
        except Exception:
            self.logger.exception("Failed to send edited-post alert: %s", event.announcement_url)
            return False
        if previous:
            self.storage.update_notification(event, now.strftime("%Y-%m-%d %H:%M:%S"))
        else:
            self.storage.record(event, now.strftime("%Y-%m-%d %H:%M:%S"))
        return True

    def _notify_event(
        self,
        event: TicketSaleEvent,
        now: datetime,
        sent: list[TicketSaleEvent],
    ) -> None:
        """Send a parsed event alert, isolating failures per event."""
        previous = self.storage.get_notification(event.dedupe_key)
        if previous:
            if previous["sale_start_at"] == event.sale_start_at:
                return
            message = build_sale_change_message(event, previous["sale_start_at"], now)
            if self.dry_run:
                self.logger.info("[DRY RUN] would send schedule update:\n%s", message)
            else:
                try:
                    self.notifier.send(message)
                except Exception:
                    self.logger.exception("Failed to notify sale-time change: %s", event.match)
                    return
            self.storage.update_notification(event, now.strftime("%Y-%m-%d %H:%M:%S"))
            self.logger.info("Sale time updated: %s | %s", event.match, event.sale_start_at)
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
        alert_key = f"unparsed:{self._post_key(post)}:{post.get('modified') or published}"
        if self.storage.alert_delivered(alert_key):
            return True
        message = build_unparsed_message(title, link, published)
        if self.dry_run:
            self.logger.info("[DRY RUN] would send fallback:\n%s", message)
            return True
        self.storage.queue_alert(alert_key, message)
        try:
            self.notifier.send(message)
        except Exception:
            self.logger.exception("Failed to send fallback alert: %s", link)
            return False
        self.storage.mark_alert_delivered(
            alert_key, datetime.now(self.timezone).strftime("%Y-%m-%d %H:%M:%S")
        )
        self.logger.info("Fallback alert sent: %s | %s", title, link)
        return True

    def _retry_pending_alerts(self, now: datetime) -> None:
        """Retry fallback alerts persisted by earlier collection passes."""
        if self.dry_run:
            return
        for alert in self.storage.pending_alerts():
            try:
                self.notifier.send(alert["message"])
            except Exception:
                self.logger.exception("Failed to retry pending alert: %s", alert["alert_key"])
                continue
            self.storage.mark_alert_delivered(
                alert["alert_key"], now.strftime("%Y-%m-%d %H:%M:%S")
            )

    def _alert_once(self, alert_key: str, message: str, now: datetime) -> None:
        """Send a health alert at most once per day for the same key."""
        if self.storage.alert_sent(alert_key):
            return
        if self._send_alert(message, alert_key, now):
            self.storage.record_alert(alert_key, now.strftime("%Y-%m-%d %H:%M:%S"))

    def _send_alert(self, message: str, alert_key: str, now: datetime) -> bool:
        if self.dry_run:
            self.logger.info("[DRY RUN] would send alert:\n%s", message)
            return False
        try:
            self.notifier.send(message)
        except Exception:
            self.logger.exception("Failed to send alert: %s", alert_key)
            return False
        self.logger.info("Alert sent: %s at %s", alert_key, now)
        return True

    @staticmethod
    def _reason(exc: Exception) -> str:
        """Short, log-safe reason for a source failure."""
        return f"{type(exc).__name__}: {exc}"[:200]

    @staticmethod
    def _post_key(post: dict[str, Any]) -> str:
        """Stable identity for a WordPress post (normalized URL, else id)."""
        return post_identity(post.get("link"), post.get("id"))
