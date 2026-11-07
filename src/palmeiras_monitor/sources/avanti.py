"""Official Avanti ticket sale source (WordPress REST API)."""

from __future__ import annotations

from ..models import TicketSaleEvent
from .base import SaleSource
from .http_client import HttpClient
from .parsing import build_event_from_post


class AvantiSource(SaleSource):
    """Monitors announcements that list the Diamante pre-sale plan."""

    name = "avanti"
    API_URL = "https://www.palmeiras.com.br/wp-json/wp/v2/posts"
    SEARCH = "Diamante"

    def __init__(self, client: HttpClient | None = None, lookback_days: int = 7) -> None:
        self.client = client or HttpClient()
        self.lookback_days = lookback_days

    def fetch_sale_events(self) -> list[TicketSaleEvent]:
        posts = self.client.get_json(
            self.API_URL,
            params={
                "search": self.SEARCH,
                "per_page": 20,
                "orderby": "date",
                "order": "desc",
            },
        )
        events: list[TicketSaleEvent] = []
        for post in posts:
            event = build_event_from_post(post, self.name, self.lookback_days)
            if event is not None:
                events.append(event)
        return events
