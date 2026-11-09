"""Source abstraction for ticket sale providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..models import TicketSaleEvent
from .parsing import build_event_from_post


class SaleSource(ABC):
    """Interface implemented by official ticket sale sources."""

    name: str
    lookback_days: int = 7

    @abstractmethod
    def fetch_posts(self) -> list[dict[str, Any]]:
        """Return the raw WordPress posts this source can see."""
        raise NotImplementedError

    def fetch_sale_events(self) -> list[TicketSaleEvent]:
        """Return parsed ticket sale events currently detectable."""
        events: list[TicketSaleEvent] = []
        for post in self.fetch_posts():
            event = build_event_from_post(post, self.name, self.lookback_days)
            if event is not None:
                events.append(event)
        return events
