"""Official Palmeiras ticket sale source (WordPress REST API)."""

from __future__ import annotations

from typing import Any

from .base import SaleSource
from .http_client import HttpClient


class PalmeirasSource(SaleSource):
    """Monitors official Palmeiras ticket sale announcements."""

    name = "palmeiras"
    API_URL = "https://www.palmeiras.com.br/wp-json/wp/v2/posts"
    SEARCH = "ingressos"

    def __init__(self, client: HttpClient | None = None, lookback_days: int = 7) -> None:
        self.client = client or HttpClient()
        self.lookback_days = lookback_days

    def fetch_posts(self) -> list[dict[str, Any]]:
        """Fetch the latest official posts that mention tickets."""
        return self.client.get_json(
            self.API_URL,
            params={
                "search": self.SEARCH,
                "per_page": 20,
                "orderby": "date",
                "order": "desc",
            },
        )
