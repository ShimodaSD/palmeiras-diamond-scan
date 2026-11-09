"""Official ticket store status probe.

The store redirects to a Queue-it waiting room while a sale is live. We only
read that redirect (never the queue page itself) to learn that sales opened and
when they were scheduled.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from urllib.parse import parse_qs, urlsplit

from .http_client import HttpClient

QUEUE_HOSTS = {"palmeiras.queue-it.net"}
TICKET_HOSTS = {"palmeiras.roboticket.com", "ingressospalmeiras.com.br"}
STORE_URL = "https://ingressospalmeiras.com.br/"
STORE_HOSTS = {"ingressospalmeiras.com.br"}


@dataclass(frozen=True)
class StoreStatus:
    """Result of probing the official ticket store."""

    active: bool
    event_key: str | None = None
    sale_start_at: datetime | None = None
    target_url: str | None = None


def parse_event_time(value: str | None) -> datetime | None:
    """Decode the Queue-it event parameter (YYYYMMDDHHMM) as local time."""
    try:
        return datetime.strptime(value or "", "%Y%m%d%H%M")
    except ValueError:
        return None


class TicketStoreSource:
    """Detects whether the official store currently has an open sale queue."""

    name = "ticket_store"

    def __init__(self, client: HttpClient | None = None) -> None:
        self.client = client or HttpClient(allowed_hosts=STORE_HOSTS)

    def check(self) -> StoreStatus:
        """Probe the store and report an active sale queue, without entering it."""
        response = self.client.probe(STORE_URL)
        if response.status_code >= 400:
            response.raise_for_status()
        location = response.headers.get("location") or ""
        if response.status_code not in (301, 302, 303, 307, 308) or not location:
            return StoreStatus(active=False)

        parts = urlsplit(location)
        if (
            parts.scheme != "https"
            or (parts.hostname or "").lower() not in QUEUE_HOSTS
        ):
            return StoreStatus(active=False)

        query = parse_qs(parts.query)
        event = (query.get("e") or [""])[0]
        target = (query.get("t") or [""])[0] or None
        if target and (
            urlsplit(target).scheme != "https"
            or (urlsplit(target).hostname or "").lower() not in TICKET_HOSTS
        ):
            return StoreStatus(active=False)
        return StoreStatus(
            active=True,
            event_key=event or "queue",
            sale_start_at=parse_event_time(event),
            target_url=target,
        )
