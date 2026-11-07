"""Source abstraction for ticket sale providers."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import TicketSaleEvent


class SaleSource(ABC):
    """Interface implemented by official ticket sale sources."""

    name: str

    @abstractmethod
    def fetch_sale_events(self) -> list[TicketSaleEvent]:
        """Return ticket sale events currently detectable."""
        raise NotImplementedError
